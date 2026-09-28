# SP-2 operational handoff: remote relay to product outcome

The paste-ready Claude continuation prompt is
[`server-pt-sp2-claude-handoff-prompt.md`](server-pt-sp2-claude-handoff-prompt.md).

Status at handoff: **incomplete**. The private `SP2-REMOTE-RELAY` stage is
implemented and registered, with offline evidence only. No episode 3 was opened
and no Packet Tracer LIVE mutation was made in this continuation. This file is
an operating procedure, not a capability or acceptance record.

## Authority and source

The controlling assignment is
[`Prompt_SP2_Generalized_DHCP_Relay.md`](../reference/server-pt/assignments/Prompt_SP2_Generalized_DHCP_Relay.md)
(SHA-256 `edeb6e45ef047a308b4d9cc6688f86ceb4cd3af44ccfd77297366c94e4889477`).
The continuation order is
`C:\Users\Andres\Downloads\Prompt_SP2_Continue_To_Completion.md`.
The active risk-L design and requirement dispositions belong in
[`server-pt-sp2-generalized-dhcp-relay.md`](change-briefs/server-pt-sp2-generalized-dhcp-relay.md).
The branch is `feature/server-pt-goal-foundations` in the
`Cisco-MCP-server-services-goal-foundations` checkout, with `cisco/main` as
its verified base. The reviewed starting checkpoint is `dbbc0297630d400c1d7c9ce327176cbff5e32433`
(tree `aebfa113b069ab1cbc8e76b129e04fb7f95aa8a2`). Resolve the current
HEAD, tree, remote and worktree status afresh; preserve every legitimate
successor. Never reset to that checkpoint.

The parent mandate already delegates in-scope implementation, causal fixes,
feature-branch publication and owned-disposable-lab LIVE investigation. Each
LIVE episode still needs a **prospective, exact-scope ledger opening**. A DRAFT,
replayed historical attempt, changed channel/build, exhausted allocation or
unknown-effect retry has no authority. One lead owns the LIVE process and file
mailbox; one writer owns this worktree. Keep SP-1, FM-REF and e1/e2 archives
immutable. No SP-3 through SP-5 or merge to `main`.

## Current private stage and evidence boundary

`SP2-REMOTE-RELAY` profile v1 binds six devices and five links from
`sp2_remote_relay_contract`: one HQ Server-PT, one BR1 PC-PT, two 1941
routers, two IE-2000 switches, and an Ethernet WAN. The HQ server is
`10.72.0.2/29`; the BR1 gateway is `10.72.32.1/29`; the helper is on BR1
`GigabitEthernet0/1` toward the server; `BR1_DATA` leases `.2`–`.3` in the
BR1 subnet. The stock `serverPool` is observed as a competitor. All fixture
literals are engineering choices, not recovered FM-REF configuration.

The stage ceiling is 3,200 operations/3,600 seconds: 25 planned setup,
3,000 product, 80 terminal, 15 protected cleanup operations. The product
scope is capped to its registered planned operations and leaves 180 ordinary
seconds for terminal observation; the final 420 seconds are protected for
owned cleanup. A theoretical trace with every IOS boot poll and every
readiness episode must stop within the cap rather than claim success.

The coordinator applies the typed pre-client E5 projection, requires exact
helper readback and access/forward/return readiness, reads that the native
DHCP process is disabled, writes and reads the named pool before process
enable, reads both physical pools around enable, then activates only the
selected PC's DHCP mode. It retains two separated client mode/IP/mask/MAC,
gateway/resolver and indexed named/default pool samples, plus a terminal
snapshot before owned cleanup. A positive result is a **sampled usable
relay-associated named-pool binding**. It is not direct observation of packet
`giaddr`, table-end/exclusive serving, `dhcpRun` causality, simultaneous
capacity or public catalog support.

Episode 1 and 2 are closed and archived. Both observed physical `serverPool`
leases; episode 2 wrote the named policy while the process was disabled and
before PC mode, removing one startup-order confound. The last inspected
active SP-2 ledger charged 229 operations and 684.87626 seconds, leaving
18,771 ordinary operations and 20,315.12374 ordinary seconds under the outer
allowance. **Reload the active ledger and verify its index before planning any
new episode**; these figures are a handoff snapshot, not a grant.

## Offline verification and checkpoint

Use only this checkout's `.venv\Scripts\python.exe`, with no custom
`PYTHONPATH`. Set a fresh test-only `PT_MCP_BRIDGE_TOKEN` in the pytest process
so bridge tests never consult the operator token file. The targeted stage
suite passed **37/37**, the adjacent SP-2 native/Q3/SP-1/authority/scale suite
passed **144/144**, and 108 related routed/relay/pool/order tests passed.
The provisional quality gate, MkDocs build, namespace inventory and
`git diff --check` passed. The full repository pytest run was **stopped at the
operator's handoff request** after reaching about 8%; it has no pass claim.
No exact-commit CI has run for this new descendant at the time this runbook
was drafted. The earlier checkpoint workflow `36356888642` succeeded in six
jobs at `dbbc029` and is not a substitute for the next commit's CI.

Before LIVE: finish the required broad tests, confirm `cisco/main` resolves,
commit the intended diff on the feature branch, require a clean tree and run
`.\.venv\Scripts\python.exe scripts\quality_gate.py --base cisco/main --delivery-commit HEAD`,
`.\.venv\Scripts\python.exe -m mkdocs build --site-dir _site`, namespace inventory and whitespace
check. Publish by fast-forward on the feature branch and inspect all six
Windows/Linux × Python 3.11/3.13 pytest, quality and docs jobs for that exact
SHA. The interactive instruction-loader check remains pending if not
observable; it cannot be inferred from file existence.

## Prospective e3 LIVE procedure

Run the CLI modules below from this checkout root as `.\.venv\Scripts\python.exe -m packet_tracer_mcp.adapters.cli.<module>` with `PT_MCP_GOVERNED_ROOT` set to this checkout. The archived e2 scripts show exact structured arguments and evidence capture; their attempt, SHA, episode and process values are historical.

1. Resolve and record the clean branch HEAD/tree, exact build `9.0.1.0858`,
   fixed `file` channel, pinned mandate hash and composed intent, manifest,
   E5/E6 hashes and candidate provenance. Re-read the active campaign index,
   all consumed accounting, current Packet Tracer process/cohort census,
   mailbox files and campaign lock. There must be no foreign process or
   document. In the exact mutation process, `sys.executable` must be this
   `.venv`, `packet_tracer_mcp.__file__` inside this checkout, and neither
   `src.packet_tracer_mcp` nor `pytest` loaded.
2. Prepare an ignored `data/services/sp2-governed/e3/lead/episode-plan.json`
   with new attempt and instance tokens, exact SHA/tree, stage/profile/fixture
   bindings, question, stop rule, permitted effects, tests and finite
   operations/seconds. The stage's 3,200/3,600 is **not** the episode or
   campaign allocation. Reserve bounded launch, retirement and contingency
   separately, staying within the freshly verified outer ledger and protected
   finalization. No retroactive extension.
3. Use the maintained `server_pt_commissioning --open-episode --campaign sp2
   --charter <mandate> --episode-plan <new-plan>` to freeze e3 **before**
   contact. The immutable e2 `lead/tools/*.txt` files are procedure references
   only: create e3-local scripts with new IDs and episode `3`; never execute
   or rewrite e2 files. The e3 launch must take a fresh exclusivity claim,
   start only an owned disposable lab, record the exact process incarnation,
   extension window, source and mailbox state, then release its launch claim.
4. Run the registered `service_qualification --execute --stage
   SP2-REMOTE-RELAY --campaign sp2 --charter <mandate> --episode 3` with its
   exact authorization ID, HEAD/tree, build/file channel, targets/models/link
   bindings, profile v1, sole `SP2-remote` step, budget/reserve, attempt,
   instance token and owned PID/path. Build the arguments from
   `stage_definition()` as the e2 `run_qualification.py.txt` illustrates;
   do not reuse e2 values. Monitor the bounded run; an unknown mutation
   outcome permits no replay or channel switch.
5. Retire through `server_pt_commissioning --retire --campaign sp2 --attempt
   <e3-attempt> --charter <mandate>`. Use only the maintained exact-owned
   graceful and authorized force path; never answer a foreign save dialog
   or terminate a foreign process. Capture an exit census and mailbox/lock
   state. Close episode 3 with the qualification record path, measured
   operations/outcome, retirement outcome and verified cleanup state. Archive
   new lead, ledger and qualification artifacts immutably with a complete
   `MANIFEST.sha256`, verify every hash and the active index, and leave e1/e2
   untouched. If cleanup or persistence is unknown, report it and stop.

A negative e3 changes the next native question; it does not complete SP-2 or
license a public capability. A private positive starts the public product
work: implement the unchanged SP2-01 through SP2-06 requirements through the
four-input `pt_apply_enterprise_services` route and default catalog, with
multiple independent pools/segments, remote sites, the selected **36
simultaneous physical leases** target, routed cold HTTP-by-IP before resolver,
DNS and hostname HTTP, controlled negatives and real 2/20/200/1000 offline
compiler/applicator/evaluator/store measurements. Only evidence-bound native
domains may be promoted. Finish with exact-SHA CI, immutable evidence and
`READY_FOR_REVIEW`; independent audit, not this runbook, accepts the phase.
