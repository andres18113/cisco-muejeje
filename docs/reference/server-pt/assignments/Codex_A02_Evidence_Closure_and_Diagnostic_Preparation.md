# A02: close the evidence sink and prepare discriminating diagnostics

**Mode: OFFLINE implementation and verification only. No Packet Tracer launch, bridge start, or LIVE dispatch is authorized by this order.**

## 1. Outcome and starting identity

Complete one delivery: fix the demonstrated terminal-snapshot loss, preserve and index the completed campaign, and prepare the two diagnostic questions below using the existing qualification components. Return one `READY_FOR_REVIEW` package with code, regressions, exact-SHA CI and draft measurement contracts. Do not return another general architecture study.

Repository: `andres18113/cisco-muejeje`.
Worktree: existing sibling `Cisco-MCP-s3`, branch `feature/server-pt-s3-dhcp`.
Start: `a02c1e0894f425f51c26e686e917cb41e59e3745`, tree `fdec9eeab3a4af4c8decfc70ac60451b746898f1`.
Verify the actual checkout, branch, HEAD, clean state, authoritative main and checkout-local interpreter before edits. Do not reset a changed tree or touch another worktree. Read the active `AGENTS.md` and `docs/engineering/standards.md`; record instruction-loading limitations honestly.

Risk L: evidence persistence and qualification execution. Record the bounded design/acceptance delta before behavior changes in the maintained record. Keep the record proportional; preserve history separately instead of appending another plan-sized narrative.

Ordinary fast-forward publication of this feature branch for exact-SHA CI is permitted by this work order. No merge, force push, main change, branch removal, subagents, capability promotion, claim reset, pool removal or credential work. No new .pts, transport, bridge endpoint or replacement executor. No unrelated formatting.

## 2. Closed campaign and immutable inputs

`SERVER-PT-D02-Q3-Q1-AUTOFIX-01` has consumed Q3 ordinal 3/3 and Q1 ordinal 2/2. There are **zero remaining LIVE attempts**. A new SHA, new nonce, reset counter, diagnostic label or application restart does not create authorization. Preserve all earlier attempts and ledger history.

Input archive:
`SERVER-PT-D02-Q3-Q1-AUTOFIX-01-FOCUSED-CLOSURE-a02c1e0.zip`
- 19,503 bytes; SHA-256 `d687f32d68cbe0cbc1059a0a4f745f2e0654ced4c8cb0d7b68a13d08669aab90`.
- Internal manifest SHA-256 `317eaf45a2a719d907dcf51f2971f4e1e76c678ad1656673ada4e761a4a2902c`.
- Q3 record `q3-2026-09-20T03-27-46Z-51ff55e7.json`, SHA-256 `7e22a2bc795fa282ce5143ef7c7bfbbaec24b02e67b12d8a52aabb1a07f89636`.
- Q1 record `q1-2026-09-20T03-31-59Z-c7bcbfc4.json`, SHA-256 `11af4155ac464c9201605e9fbe4c53dd96db22d9b0bc60322b05dcedaa2da917`.

Reverify source bytes before archiving. Reuse the existing immutable archive/index mechanism once, with hashes and source identities. Do not duplicate the whole historical corpus. The new ZIP cites a ledger hash but does not contain that ledger; resolve its existing durable location and verify it rather than inventing a replacement chain.

The review closes the previous F1 shared-writer, F2 readiness and F4 exact-retention counterexamples within their reviewed offline scope. F3's strict reader is improved; its terminal persistence is not closed. Do not reimplement those settled designs or claim full product acceptance.

## 3. A02-E1: terminal default snapshot is observed but not persisted

Evidence at the start SHA:
- `application/use_cases/qualify_server_services.py::_q3_snapshot_default` appends only to `_Execution.default_pool_snapshots` and differences.
- `_run_q3` concludes `M-DHCP-1` using a copy from `_native_default_facts`, finishes `Q3_SETUP`, then on the stopped branch performs `before_cleanup` and returns.
- The delivered Q3 record has only `before_e5` and `after_setup` snapshots. Operation 32 is a correlated read with an empty `purpose`; inspection of this branch identifies it as the pre-cleanup read. Its returned pool values are not recoverable from the delivered record.

Required correction:
1. Each acquired default snapshot must reach the durable run evidence, including observations after a stop and observations during finalization. Use one authoritative sink and the existing store/transition machinery. Do not add an event-sourcing framework or another persistence subsystem.
2. Preserve the snapshot's exact raw bounded fields, label, observed/unobserved cause, differences and association with the counted operation. Assign a precise operation purpose before dispatch, not retrospectively from ordinal assumptions.
3. Preserve the first primary failure. A final read error or store error is additional evidence, not permission for new effects and not a replacement for the primary cause.
4. A read that cannot be afforded or performed is explicitly not observed. Do not introduce an extra bridge operation only to repair documentation; record the observation already performed and account for any design change in the same budgets.
5. Keep the original historical JSON and its hashes unchanged. Add an external review limitation saying that the pre-cleanup payload is missing. Never reconstruct it as equal to `after_setup` and never rerun the exhausted attempt to fill it.

Acceptance (real coordinator and store, RED first):
- Trigger early stop on a default change; return a deliberately different value in the final snapshot. Reload the persisted terminal record and assert all three actual observations, their labels and operation association, plus the unchanged primary cause.
- Cover final-read malformed/error/unobserved outcomes, insufficient remaining allowance, and persistence failure. No later experimental effect may occur, and owned finalization remains bounded.
- Keep the success-path snapshot trace and semantic restoration controls green. The test oracle is the supplied native-state transition/call log, not a copy of the projection algorithm.

Future diagnostic prose must distinguish `no explicit setter targeted the native default` from `the default's values did not change`. Correct the current projection and future omission prose (`53` versus the current budget); do not edit historical evidence or create a new general rule system.

## 4. Prepare diagnostic D-DHCP: identify when the native default changes

Observed, not inferred: between the existing pre-E5 and post-setup snapshots, `serverPool` changed network/mask/start/end to `192.0.2.0`, `255.255.255.0`, `192.0.2.0`, `192.0.3.255`. Name, maximum 512, zero gateway and zero DNS stayed the same. The intended one-address pool was also observed. The old record does not identify which operation caused the default transition.

Prepare a *new, not authorized* measurement profile using the existing runner, product writers, native readers and operation ledger. Keep dispatch unavailable without an independently approved, exact-scope authorization. Do not rename an old Q3 retry.

Discriminating sequence for its draft contract:
- Create the same exact disposable fixture and establish the disabled native baseline with clients not activated.
- Observe immediately after configuring only the server's static address through the existing E5 path, before any DHCP-server setter or client-mode activation.
- If the draft profile permits continuing after a fully observed native transition, configure only the intended pool while the process remains disabled, then observe both pools.
- Only under the future explicit authorization, enable the process and observe again.
- No client acquisition, no DHCP event observer, no default-pool setter/removal/reset, and no restoration of the default by rewriting its values.

The native transition is the dependent variable of this proposed diagnostic, not an accepted new product invariant. Preserve every change rather than learning an allowlist from it. An unknown effect, wrong identity, malformed/incomplete inventory or foreign subject still stops. If an existing product writer cannot support this decomposition without changing its semantics, document that exact seam and prepare the minimal reviewed extension rather than copying its setters or executing an ad hoc script.

Offline output: generated/proposed sequence, exact target/effect list, typed records, before/after oracle tests, budget arithmetic including finalization, and a draft authorization with **no granted status**. A finite native default transition must not be conflated with client acquisition or serving authority.

## 5. Prepare diagnostic D-WEB: distinguish reachability from the client reader

Observed: Q1's four readiness reads ended with all six exact ports up. Both page handles read the new marker, but the HTTP positive did not produce fresh content. The HTTPS positive and both negatives never ran. The current runner uses an 8-second fetch timeout and the same polling interval. This is neither a demonstrated HTTP/HTTPS failure nor proof that increasing the timeout fixes it.

Prepare a narrow diagnostic in the existing components, not another full page-ownership Q1:
- Carry the measured link fields separately from any documented forwarding/STP/reachability observation. Reuse existing typed command/observer seams where available; check every previously unused vendor method and result contract against the installed reference.
- Retain actual listener enabled states and port numbers, selected URL/path, client ownership and mode, initial page content/marker relationship, request-start result and timestamped bounded poll outcomes. Never infer a field the reader did not observe.
- Define a same-fixture positive/control comparison sufficient to locate the failure boundary (network path versus listener/request versus polling/reader). Avoid adding effects that cannot distinguish those alternatives. State uncertainty when only layer-1/2 readiness is observable.
- Record timing and remaining budget per call. Do not enable PortFast, alter forwarding configuration, switch transport, add unconditional waits, register unqualified events or issue automatic second fetches as a purported fix.
- No negative listener claim from a timeout. No real TLS guarantee. No repeated shared-page-table measurement; that question already has its own attributed evidence.

The draft LIVE plan must specify any owned clients/requests, their cleanup and new limits explicitly. This order authorizes preparing and testing that plan offline, not executing it. Existing Q1/Q3 attempts remain spent.

## 6. Delivery gates and output

Use checkout-local tools and focused paths. Locate symbols before reading ranges, inspect targeted diffs, and run the narrowest meaningful regression first. Never run `ruff --fix src` or mass-format unrelated files. Do not reduce assertions, capability gating or evidence requirements to achieve green.

Run focused regressions, affected/coexistence tests, the full offline suite, namespace inventory, documentation build, whitespace check, and the clean delivery gate against the verified authoritative main. Publish only the feature branch by ordinary fast-forward; inspect exact-SHA CI, including its matrix. Attribute earlier checks to their original SHA.

Deliver one compact report containing:
- final SHA/tree and independently inspectable CI;
- A02-E1 causal RED/GREEN, persisted terminal evidence regression and closure status;
- byte-preserved campaign archive/index and exhausted attempt counters;
- two concrete diagnostic profiles with typed observations, budgets, expected controls and draft authorization requirements;
- all remaining product limitations, especially unqualified acquisition, listener isolation and Q1b/Q2.

No Packet Tracer process needs to be running for this work. The previous permission to manage owned processes does not authorize a new exhausted-campaign measurement. Do not launch or contact Packet Tracer in this offline delivery. Do not self-approve or merge.
