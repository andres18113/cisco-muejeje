# Batch handoff — Q0-file (input), Q1-file, Q0-HTTP

Assignment: `C:\Users\Andres\Downloads\Batch_Q1_and_Q0_HTTP.md`.
Executed SHA `0850de3dd94c8ada25c5b493e5638e6b0ce0351d`, tree
`acc6caf6f45bfe7afcaf3a08531993703d28eebf`, branch
`feature/server-pt-s4a-qualification-runner`, worktree `Cisco-MCP-s4a`.
Source identity, clean tracked tree, package origin and published upstream were
re-verified immediately before each invocation and matched every time.

Both authorized scopes executed exactly once. No source edit, commit, push,
dependency change, new probe, GUI automation, capability promotion, claim reset
or protocol change was made. The offline suite was not re-run.

## Compact decision table

| Fact | Q0-file | Q1-file | Q0-HTTP |
| --- | --- | --- | --- |
| Run id | `2026-09-18T23-39-18Z-b68e4a7b` | `2026-09-19T00-13-08Z-985c1368` | `2026-09-19T00-20-05Z-edbbc347` |
| Authorization | `Q0-file-0850de3-01` | `Q1-file-0850de3-01` | `Q0-http-0850de3-01` |
| Channel / liveness | file / `heartbeat_fresh` | file / `heartbeat_fresh` | http / `webview_polling` |
| Observed build | 9.0.1.0858 | 9.0.1.0858 | 9.0.1.0858 |
| Exit status | 0, `completed` | 0, `completed` | 0, `completed` |
| Budget used | 19/20 ops, 14.219/300 s | 46/60 ops, 39.812/600 s | 19/20 ops, 6.437/300 s |
| Reserve borrowed | no (5 ops / 60 s) | no (10 ops / 120 s) | no (5 ops / 60 s) |
| Refusals / failures | none | none | none |
| Cleanup | `unknown`, residue cb2+cb3 | `clean`, no residue | `unknown`, residue cb2+cb3 |

Exit status, hypothesis support and cleanup are independent: all three runs
exited 0, only Q1 finished CLEAN, and no run promoted any capability.

## Stage 1 — Q0 file channel (accepted input, not re-executed)

Record `q0-2026-09-18T23-39-18Z-b68e4a7b.json`, SHA-256
`1a6ee0811c2df36e841a1eec73f8885b20ec892c6f23f3f94cb90f59c517c955`.
Baseline observed empty. Two `send` operations recorded `result=not_applicable`;
the other 17 ledger entries are `correlated`.

| Measurement | Conclusion | Causes / limitations |
| --- | --- | --- |
| M-ENG-1 | supported_in_sample | none |
| ATOM-1 | supported_in_sample | `evaluation_scope: separate_evaluations`; bounded one-pair sample, not universal atomicity, not cross-channel exclusion, not exactly-once delivery |
| M-UNREG-1 | supported_in_sample | one source object / one event kind; release proven only by absence after a control event |
| M-UNREG-2 | supported_in_sample | supports the **inert fallback** hypothesis only; `safe_zero_event_release_established=false` |
| M-HTTP-1 | not_evaluated | `prerequisite_absent` — no HTTP server in the fixture |

Releases: cb1 `released_in_sample`; cb2, cb3 `release_attempted_unverified`;
run bag released; `__MCP_E6Q_PC1` removed. Both restoration reads empty,
`restoration_proven: true`, `dirty_state: unknown`.

## Stage 2 — Q1 file channel

Record `q1-2026-09-19T00-13-08Z-985c1368.json`, SHA-256
`a0e2f93820d980e98551b0106615d86a89f8fb08e422b82ca01c09692fc5b005`.
Started 2026-09-19T00:13:07.687Z, finished 00:13:48.660Z. Baseline empty.
Fixtures `__MCP_E6Q_SRV` (Server-PT, 192.0.2.10), `__MCP_E6Q_PC1` (192.0.2.11,
DNS 192.0.2.10), `__MCP_E6Q_PC2` (192.0.2.12), `__MCP_E6Q_SW` (2960-24TT), three
links. Record-level limitation `e5_endpoint_dispatch:accepted`.

| Measurement | Conclusion | Causes / limitations |
| --- | --- | --- |
| M-HTTPS-1 | INCONCLUSIVE | `marker_write_failed`; `File not exist: mcpq-525aba9800c94c78-h.html`, `-s.html`. `http_process_found` and `https_process_found` true, `object_identity_equal` false, limited by `reference_equality_is_not_page_ownership` |
| M-HTTPS-2 | INCONCLUSIVE | positive HTTPS-only fetch and both negatives all `unestablished:inconclusive:no_response_within_deadline`; `no_same_mode_positive_control` for both negatives; `no_qualified_listener_refusal_observable`; `fresh_content_not_retained` |
| M-DNS-3 | supported_in_sample | `__MCP_E6Q_PC1` → `192.0.2.10`; unset `__MCP_E6Q_PC2` → `0.0.0.0`; `one_client_one_value` |
| M-DNS-1 | not_evaluated | `not_admitted_by_budget` |
| M-DNS-2 | not_evaluated | `not_admitted_by_budget` |

Releases: clients `https-positive`, `http-negative`, `https-negative` all
released; all four fixtures removed. `restoration_proven: true`,
`engine_residue: []`, `dirty_state: clean`.

**Observation kept as measured, not reconciled:** baseline read
`backend_managed_device_count: 0`; both restoration reads show
`backend_managed_device_count: 1`, a PT-created `Power Distribution Device0`.
Semantic device count and link count returned to 0 in both reads and the runner
concluded `clean`. Reported as observed; the stage record was not modified.

## Stage 3 — Q0 HTTP channel

Record `q0-2026-09-19T00-20-05Z-edbbc347.json`, SHA-256
`5d0b919f04a83e516fcbefa0a41c59b77539e73334738b3780a05723cb4b40aa`.
Started 2026-09-19T00:20:04.863Z, finished 00:20:14.782Z. Transport fixed at
00:20:07.799Z with `webview_polling`; bridge port 54321 verified free
beforehand. Baseline empty. Two `send` operations `not_applicable`, 17
`correlated`, 0 refused.

| Measurement | Conclusion | Causes / limitations |
| --- | --- | --- |
| M-ENG-1 | supported_in_sample | none; nonce matched, key owned at read and write |
| ATOM-1 | **INCONCLUSIVE** | cause `separate_evaluations_not_observed`; `evaluation_scope: unknown`; ordered log retained (`A:check, A:claimed, B:check, B:refused`); adds `http_channel_may_join_queued_commands_into_one_batch` |
| M-UNREG-1 | supported_in_sample | `HostPort.ipChanged` delivered, uuid `{02a8a50f-6a1e-0ec5-fc34-0763080aa4ad}`; release via `_ScriptModule.unregisterIpcEventByID`; same two limitations as Q0-file |
| M-UNREG-2 | supported_in_sample | inert fallback only; `safe_zero_event_release_established=false` |
| M-HTTP-1 | not_evaluated | `prerequisite_absent` |

Releases: cb1 `released_in_sample`; cb2, cb3 `release_attempted_unverified`;
run bag released; `__MCP_E6Q_PC1` removed. Both restoration reads empty
(0 semantic, 0 backend-managed, 0 links), `restoration_proven: true`,
`dirty_state: unknown`.

The HTTP ATOM-1 result does not borrow the file channel's
`separate_evaluations` observation, and the file result does not qualify HTTP.

## Process boundary

| Instance | Role | State |
| --- | --- | --- |
| pid 51840, started 18:37:53 | ran Q0-file | gone before this batch began |
| pid 50848, started 19:04:35, parent 37616 | ran Q1-file | retired by the operator between scopes |
| pid 28652, started 19:18:13, parent 37616 | ran Q0-HTTP | **still running at handoff** |
| pid 40684, started 18:37:58 | `--progress-bar-server`, child of the dead 51840 | windowless orphan, owns no mailbox, left untouched |

Each stage ran in its own process. The mailbox
`%LOCALAPPDATA%\packet-tracer-mcp\bridge` held only `alive.txt` before and after
every run: no second writer, no pending request. Port 54321 was free before the
HTTP run.

**Retirement of pid 28652 is incomplete.** One normal close
(`CloseMainWindow`) closed the extension's "Logs - MCP BUILDER" window instead
of the application, which kept running and responding — the same behaviour seen
with pid 50848. Completing it requires handling a save prompt, which is GUI
automation and out of scope, so it is returned to the operator. No kill was
attempted.

**Cleanup limitation, preserved as UNKNOWN:** `observer:cb2` and `observer:cb3`
were marked inert and their detachment was not observed, in both Q0 runs. That
is `release_attempted_unverified`, not proof that two callbacks remain attached,
and an empty workspace does not establish detachment either. Retiring pid 28652
establishes a fresh process boundary; it does not convert either run's UNKNOWN
cleanup into CLEAN.

## Eligible next work

- **S1b content contract is not yet decidable.** M-HTTPS-1 is INCONCLUSIVE
  because the marker write failed, so neither `shared_content` nor
  `SetHttpsContent` has measured support. `object_identity_equal: false` is
  explicitly not page ownership. Selecting either model now would exceed the
  observation. A further authorized HTTPS content measurement, addressing the
  marker-write path first, is the prerequisite.
- **A bounded S2 design is supportable under stated limits.** `M-ENG-1` holds on
  both channels, so run-bag persistence across separate evaluations may be
  relied on for the sampled build and channels. `ATOM-1` may be assumed only on
  the file channel; on HTTP the evaluation scope is unknown, so no S2 mechanism
  may depend on separate-evaluation non-interleaving over HTTP.
- **Event-driven product verification stays gated under R-EVT-05.** M-UNREG-1
  supports release using the event-supplied source identity, but M-UNREG-2
  records no safe zero-event release on either channel. The planned fallback
  therefore stands: supporting SMTP_DELIVERED evidence, no POP3 retrieval claim,
  and DHCP read-back at most UNKNOWN pending its own qualification.
- **M-DNS-3** qualifies only its exact reader, model, build and channel sample:
  `DnsClient.getServerIp` returned the configured resolver, and the unset
  representation on this build is `0.0.0.0`.

Nothing above is implemented, promoted or authorized by this measurement batch.
No Q1b, Q2 or Q3 run and no catalog promotion is authorized by it.
