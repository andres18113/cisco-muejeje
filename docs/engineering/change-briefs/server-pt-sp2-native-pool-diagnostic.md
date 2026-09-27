# SP-2 native pool discrimination campaign (v1)

Risk: L. This changes LIVE qualification authority and evidence interpretation. The supplied SP-2 work order is archived byte for byte at `docs/reference/server-pt/assignments/Prompt_SP2_Generalized_DHCP_Relay.md` (SHA-256 `edeb6e45ef047a308b4d9cc6688f86ceb4cd3af44ccfd77297366c94e4889477`). The accepted starting commit is `c6a77782d884cf2b2c21859146f5b17d19bb4c6e` on `feature/server-pt-sp2-campaign` in the `Cisco-MCP-sp2-campaign` sibling worktree.

## Intended outcome and scope

Create a fresh experimental SP-2 campaign identity, separate finite ledger and a narrowly scoped native stage that discriminates physical named-pool serving from native `serverPool` serving using client and lease-table observations. The first fixture is two PC-PT clients on one owned access segment with a Server-PT; it retains the established Q3-FL setup, native-default policy, typed acquisition and bounded readers. This stage answers a native hypothesis only. Generalized local capacity, multiple subnets, relay, routed services and product support remain SP-2 work outside this slice. A later relay smoke stage must have its own fixture, preconditions and measurement; none is claimed here.

## Requirements and acceptance

| Requirement | Offline acceptance |
| --- | --- |
| Fresh authority | The work-order digest, campaign ID, prefix and ledger differ from SP-1 and prior DHCP campaigns; wrong charter/stage/attempt refuses before contact. |
| Finite budget | Episode allocations fit 20,000 operations and 21,600 seconds, protecting 1,000 operations and 600 seconds for finalization. No attempt-count quota. |
| Physical pool identity | An exact client IP/MAC row in the named pool plus a complete absent row in `serverPool` supports named serving; exact native serving is a negative finding; conflicts, duplicate identities, missing rows or unreadable scans do not support named serving. |
| Evidence boundaries | Configuration and in-range addresses alone never establish a lease; every selected client has a result. Explicit acquisition, renewal and total capacity are independent claims. |
| Stage governance | The new stage runs only through the existing file-channel qualification runner with exact build, campaign authority, source/tree, process and clean owned-lab gates. |

## Architecture and invariants

The domain stage definition owns the fixed experimental fixture and budget. A domain evidence function classifies typed per-client attribution. The existing application qualification runner performs the controlled probe sequence and persists the extra SP-2 measurement. The CLI and campaign ledger bind the new charter and phase. No public service input, catalog promotion, second execution engine, new Packet Tracer API, or general runtime behavior is added. The prior Q3-FL stages and their records keep their existing identity and semantics. An unobserved mutation remains outcome-unknown and permits no retry.

## Verification design

Unit tests cover named, native, duplicate/ambiguous and unreadable outcomes. Contract tests check exact stage/campaign/charter binding, admission and finite ledger. Focused qualification tests exercise the existing fixture path with controlled offline boundaries; related campaign and stage suites, Ruff, documentation build, whitespace and the exact clean-delivery gate close the slice. LIVE, native capacity and relay acceptance are not applicable to this offline implementation and require separately observed campaign episodes.
