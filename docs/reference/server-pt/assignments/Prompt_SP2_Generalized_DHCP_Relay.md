---
work_order: SERVER-PT-SP2-GENERALIZED-DHCP-RELAY-01
version: 1.0.0
issued_on: 2026-09-27
phase: SP-2
risk: L
predecessor: SP-1 independently accepted at c6a77782d884cf2b2c21859146f5b17d19bb4c6e
delivery_boundary: READY_FOR_REVIEW
---

# SP-2 — Generalized DHCP and relay

## 1. Mission and authority

Deliver reusable Server-PT DHCP for selected wired PC-PT clients on local and remote subnets, including relay where the declared authority requires it. The maintained public product must configure the intended policy, obtain usable native leases, retain exact client/pool evidence, and perform cold HTTP by IP followed by DNS/hostname HTTP across admitted routed paths. A renamed two-client whitelist does not satisfy this mission.

This is the complete SP-2 assignment when the operator supplies it for execution. Implementation, causal autofix, offline delegation, feature-branch publication and owned-disposable-lab LIVE investigation/acceptance are authorized within the boundaries below. You decide the architecture details, pool strategy, experiments and execution order. Do not seek approval after routine technical decisions or stop at a plan when authorized work remains. Stop at `READY_FOR_REVIEW`; independent review, not self-review, accepts the phase. Do not implement SP-3 through SP-5 or merge to main.

## 2. Establish the accepted starting point

Repository: `andres18113/cisco-muejeje`.
Worktree: `Cisco-MCP-server-services-goal-foundations`.
Branch: `feature/server-pt-goal-foundations`.
Accepted predecessor commit: `c6a77782d884cf2b2c21859146f5b17d19bb4c6e`.
Accepted tree: `ebd9bab939741b9ef4c1fde4820136dd596d98cc`.
Last verified main: `6263344e31ba3b0de6539d652f2cd06fc73a3562`.

Resolve current references, ancestry, pending changes and environment before editing. Preserve legitimate successors and unrelated changes; never reset to this checkpoint. Read this checkout's `AGENTS.md`, tool-specific instructions and `docs/engineering/standards.md`. Use its own virtual environment and canonical `packet_tracer_mcp` namespace. A loader check that cannot be observed remains pending, not an invented success or a reason to abandon otherwise authorized work.

SP-1 R1/R2 are closed: preserve chronological revocation of pending routed permissions, direct-neighbor egress proof, durable shared causes, client-local versus shared failures and cold-request ordering. Historical W1/W2 remains at `a04369a`; corrected e5 W2 executed at `849e497`. No observation changes source identity. Reuse accepted S0/S1/S4a and the existing S3 implementation rather than restarting them.

## 3. Reference and design decisions

Canonical reference: `docs/reference/final-muejeje/Final-Muejeje.md`, FM-REF 1.0.0, SHA-256 `090238b17ddfc95b8f2dc1d637f18b462ad19b6ab5c0eec4eaf357ccf0cae37a`. Preserve its bytes, encoding, IDs, provenance and source-gap register.

Read its server roles, recoverable wired PC-PT inventory, subnet populations and gaps. It identifies a nominal DHCP server at `172.16.100.6/28`, but does **not** establish pools, exclusions, client DHCP modes, authority per segment, relay configuration or all physical server attachments. Observed addresses and subnet populations are not lease records or DHCP client counts.

Define an explicit provisional SP-2 requirement/fixture matrix from those capability dimensions. Separate source facts, engineering choices and unknowns. You may choose addresses, clients, policies, pool ownership and topologies for disposable fixtures without asking permission; do not claim those choices recover missing facts about Final-Muejeje. Exercise different data prefixes, names, capacities and placements rather than making its literals production special cases. Full-topology replication is outside this phase.

Before behavior changes, write one proportional risk-L brief at `docs/engineering/change-briefs/server-pt-sp2-generalized-dhcp-relay.md`: intended outcome, admitted policy/capacity domain, requirements paired with acceptance, architectural ownership, invariants and tests. Keep decisions there and continue; the brief is not a new approval checkpoint.

## 4. Required product behavior

**SP2-01 — Authority and policy.** Derive one intended DHCP authority per selected client segment from the intent before E5/E6 compilation. Preserve IOS/Voice authority on segments that select it. Where Server-PT is required, neither router DHCP nor relocating clients to the server subnet is an acceptable substitute. Reject conflicting or ambiguous authorities and invalid address/exclusion/capacity policies before effects. Public intent and capability constraints must explain supported and refused inputs.

**SP2-02 — Native pools and capacity.** Decide native `serverPool`, named-pool handling and startup ordering from vendor contracts and discriminating measurements. Establish which physical pool actually serves each admitted segment. Prevent an unintended native default from silently serving a competing policy. Use existing typed actions/readers; a stored pool or successful setter is not an allocated lease. Cover multiple independently configured pools/segments and simultaneous clients, not serial single-client demonstrations represented as aggregate capacity.

**SP2-03 — Routed relay.** Extend the maintained plan-derived effect/evidence closure to the necessary relay interfaces, selected server address, client access path and forward/return routes. Observe relay configuration and relevant operational prerequisites through attributed supported readers. Prove actual lease assignment from the intended authority with clients on other subnets and sites. Relay configuration alone, ordinary unicast reachability, or an address merely falling in range is insufficient. Required shared-path failures block their dependents without contaminating independent segments.

**SP2-04 — Lease identity and evidence.** Keep duplicate address/MAC and competing-pool checks active after any selected client's local failure. Normalize equivalent identity representations without hiding conflicts; index every fresh lease scan once and retain repeated rows. Preserve per-client readings, first local failure and later shared contradictions. Admission to services requires a usable address/mask, intended gateway/resolver, stable client identity and positive attribution to the intended physical pool. Missing or unreadable observations remain unknown, not fabricated changes or absence. Do not require explicit `dhcpRun` causality, renewal or universally calibrated table exhaustion merely to prove ordinary usability; report those claims separately.

**SP2-05 — Public service integration.** Preserve the four public inputs of `pt_apply_enterprise_services`; add no experimental public override or parallel service engine. Reuse S3 lease gating and SP-1 routed readiness with the observed DHCP address, not a statically assigned stand-in. After necessary DHCP acquisition traffic, the client's first application test is HTTP by IP with a fresh marker: no preparatory ping, DNS query, warm-up fetch or static client fallback. Then verify the DHCP-provided resolver, DNS and hostname HTTP. Persist every selected client, including refused or blocked ones. Preserve already established results without reusing invalidated prerequisites or reapplying the whole network.

**SP2-06 — Scalable implementation.** Algorithms operate on N clients and topology-derived groups. Avoid all-pairs traffic, per-client complete lease scans, repeated whole-workspace inventories and full shared evidence copied per client. Readiness/scan budgets follow actual work and retain finite bounds. Keep domain rules backend-neutral, orchestration in application, and Cisco APIs/transport/persistence in infrastructure. Extend current layers; do not create another orchestration framework.

## 5. Acceptance and useful verification

Deliver representative native acceptance through maintained deployment and the registered product route with the default catalog:

- Local generalized DHCP with meaningful simultaneous capacity and varied addressing/policy, beyond the accepted two-client template.
- A remote/relay workload spanning multiple client subnets and sites, with simultaneous independent pool use and working subsequent routed services.
- Controlled negatives that discriminate wrong authority/pool, duplicate identities, wrong relay or return path, and local versus shared observation failures. Select the appropriate layer: deterministic zero-effect admission properties can be proved in real-composition integration tests; native hypotheses require native measurements.

Before choosing native scale, derive a concrete demand target from the recoverable non-IoT PC-PT inventory and explicitly selected fixture policies. Demonstrate simultaneous native leases sufficient for the largest selected data-segment demand in that target, or report exactly what remains blocked. Do not treat every observed device as a DHCP client, call a configured pool limit measured capacity, or declare the phase complete after increasing a whitelist from two to three.

Exercise offline 2/20/200/1000-client orchestration, reporting actual constructed N when fixture allocation differs. Use real compilers, applicators, evaluators and persistence with explicitly substituted backend boundaries. Measure dispatch/scan counts, lookup work, response and record bytes, elapsed time and peak memory. Native capacity and offline orchestration scale are different results.

Write reproducible failing regressions for causal defects, then fix the owning layer. Cover malformed/foreign/stale readings, uncertainty after dispatch, repeated/conflicting leases, receiver replacement, cancellation, record-write failure and finalization where affected. Test generated scripts against independent stateful stubs, not copied product predicates. Preserve SP-1 and existing DHCP/Voice/Printer/CP-SCALE regressions. Do not demand a fixed number of adversarial review rounds; inspect findings and close substantive defects.

## 6. LIVE autonomy and protected resources

Use new SP-2 campaign/episode identities, not renewed historical grants. Prospectively record finite campaign and episode operation/time allocations with protected finalization reserves, within existing operator/platform limits; do not rewrite consumed accounting or enlarge an exhausted allowance retroactively. There is no arbitrary two-attempt quota. A failed experiment should change the next causal question, not trigger an identical retry until green.

One lead owns LIVE and the shared mailbox. Offline subagents may investigate or review independent work; one writer per worktree. Before effects, prove exact source/tree, build, fixed channel, process/cohort identity, checkout-local interpreter/package, empty owned baseline and no pytest process. The initial target build is 9.0.1.0858 and the existing file-qualified path; other channels/builds cannot inherit its support.

Preserve fail-closed authority and local receiver-continuity controls without claiming in-band Packet Tracer fencing. An outcome-unknown mutation permits no automatic retry or cross-channel fallback. Preserve its quarantine and evidence. You may create, inspect, restore, discard and retire owned disposable labs, including exact-owned-cohort force retirement after bounded graceful failure through the maintained machinery. Never answer a foreign document's save prompt or terminate an unowned process.

Do not mutate original Final-Muejeje/CP-SCALE labs, IoT work, other worktrees or historical archives. No new bridge, raw-command escape hatch, unrelated refactor, security relaxation or speculative capability promotion. Any new native API must be checked against the vendor reference and qualified before it becomes product evidence.

## 7. Completion and handoff

Work to the phase outcome, not a sequence of tickets. Make routine reversible decisions, give short progress updates and continue independent authorized work while a dependency is investigated. Ask only for a material protected-scope change or genuinely missing input that prevents further progress. If a required native domain cannot be established, preserve the implemented work, failed alternatives and discriminating evidence, then deliver a concrete scope decision; do not silently substitute another authority or label the requirement complete.

Run focused, affected and proportionate broad verification, namespace/docs/whitespace checks, and the clean exact-SHA delivery gate. Publish fast-forward on the feature branch for exact-SHA CI and retain per-job outcomes and skip reasons. Archive native records with source/process/build/channel/catalog identity, immutable manifests and cleanup outcomes. Populate support entries only for evidenced policy domains; candidate seams remain internal.

Return `READY_FOR_REVIEW` with commit/tree, requirement dispositions, admitted/refused support matrix, native versus offline scale, decisive evidence, cleanup state and remaining limitations. Preserve a concise handoff across context compaction. Do not stop with “the next step is testing” when testing is authorized, and do not start SP-3, merge to main or create the Final-Muejeje branch.
