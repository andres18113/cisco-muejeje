# SP-1 — Routed DNS and HTTP: extend S1/S1c

**Work order:** `SERVER-PT-SP1-ROUTED-DNS-HTTP-01`  
**Version:** 1.0.0 · 2026-09-26  
**Risk:** L  
**Authority:** implementation, causal autofix, offline delegation, feature-branch publication and owned-laboratory LIVE for SP-1 are authorized by this work order.  
**Delivery boundary:** `READY_FOR_REVIEW`; independent technical acceptance is not delegated.

## 1. Outcome and phase boundary

Complete SP-1 through the maintained product: selected wired, statically addressed PC-PT clients consume DNS and HTTP from Server-PT hosts across VLANs, subnets and sites. Demonstrate HTTP by IP, DNS resolution and HTTP by hostname, with plan-bound network prerequisites, per-client evidence and durable results. Preserve existing local/L2 service behavior and CP-SCALE/Voice/Printer behavior.

This is an implementation-and-acceptance mission, not a request for another plan. Choose the design, experiments and causal fixes necessary to finish the phase. Work autonomously until its completion criteria are satisfied or an evidenced external blocker makes further authorized progress impossible. Routine choices, tests, commits and new experiments do not require renewed permission.

Only SP-1 is active. Do not implement generalized DHCP/relay (SP-2), SMTP/POP3 completion (SP-3), HTTPS qualification or a new nslookup feature (SP-4), or release integration (SP-5). Preserve those existing components and their current claims. Do not replicate the complete Final-Muejeje topology, merge to main, or create its future implementation branch. SP-2 starts only after the independent technical reviewer explicitly passes SP-1 and issues its next work order.

## 2. Reconcile the checkout; incorporate the supplied reference

Repository: `andres18113/cisco-muejeje`. Continue on `feature/server-pt-goal-foundations` in its existing governed worktree, normally `Cisco-MCP-server-services-goal-foundations`, with its own virtual environment and editable install. Last reviewed baseline: `890c950663d035cfe3d182c97a16a415bbb24522`. The last observed authoritative main is `6263344e31ba3b0de6539d652f2cd06fc73a3562`; verify the actual remote alias, refs, ancestry, SHA/tree, worktree and interpreter before edits. Inspect intervening work; never reset it to the older baseline or reimplement completed corrections.

Read this checkout's `AGENTS.md`, `CLAUDE.md` and `docs/engineering/standards.md`. Report an unobservable interactive instruction-loader check as pending, not passed; that alone does not block ordinary authorized work.

The operator has already prepared the final reference document:

```text
Source:      C:\Users\Andres\Desktop\Final-Muejeje.md
Destination: docs/reference/final-muejeje/Final-Muejeje.md
Document:    FM-REF, version 1.0.0
```

The supplied conversation copy has 233,815 bytes and SHA-256:

```text
090238b17ddfc95b8f2dc1d637f18b462ad19b6ab5c0eec4eaf357ccf0cae37a
```

Read the Desktop file directly, hash it, and incorporate it byte-for-byte at the destination. Preserve its language, version, appendix and source-gap declarations. Use a path-specific Git attribute if needed to prevent newline conversion of these authoritative bytes; do not change repository-wide text policy. Verify the committed blob bytes against the source. If an existing destination differs, preserve it and resolve the provenance collision rather than overwriting silently. A differing Desktop digest is a version discrepancy to investigate, not permission to substitute an older copy.

Do not regenerate or repair this document. Its `REFERENCE_CONSOLIDATED_WITH_SOURCE_GAPS` status and `exact_replication_ready: false` remain meaningful. Publication statements describe issuance history; record the actual incorporation commit in the SP-1 brief rather than rewriting the source. Its embedded `source_sha256` identifies the underlying export, not this complete Markdown file.

Read its overview, network/service tables and gap register first; consult the raw appendix only for a concrete question. Use established facts as future requirements context, never as runtime evidence. Do not invent missing interfaces or links. SP-1 uses separate, explicitly designed representative fixtures, so unresolved reference links must not become a pretext to stop unrelated routed-service work.

## 3. Architecture and scope decisions

Before behavior changes, record one proportional design and requirement-to-test map at `docs/engineering/change-briefs/server-pt-sp1-routed-dns-http.md`, or in an existing unambiguous SP-1 brief. Map the requirements below to existing IDs where applicable. Record architecture, effect closure, failure semantics, support domain and verification before continuing; do not request another planning approval inside this authorized scope.

Inspect the actual flow from the registered `pt_apply_enterprise_services(intent_json, deployment_id, packet_tracer_version, run_label="")` through shared session composition, enterprise compilation, configuration/control-plane execution, service application, readiness and persistence. Preserve the four public inputs and avoid support-override flags.

Reuse the existing planners, compilers, execution ports, IOS query/parser registry, route/forwarding observations, runtime and campaign infrastructure. Add only missing responsibilities in their owning layers. Routing belongs to foundational/control-plane configuration, not a second router configurator inside E6. No replacement transport, protocol or monolithic acceptance runner is requested.

Required topology families are IPv4 unicast: existing local/L2 paths, inter-VLAN routing on one gateway, and multi-router/multi-site routed paths. Include separate DNS and HTTP hosts; co-location is not a requirement. Static routes are an adequate initial mechanism. Preserve existing routing-protocol paths and reuse them where appropriate, without making a new routing protocol, NAT, VPN, IPv6, HA or wireless subsystem part of this phase.

Implement a reusable admitted domain, not a whitelist of fixture names, prefixes, two clients or one switch. Unsupported shapes must still refuse precisely before effects. The old S1c single-gateway boundary is expressly expanded for SP-1; historical records and old grants are not changed.

## 4. Required behavior and acceptance

**SP1-01 — Plan-derived admission and effect scope.** Derive clients, service hosts and forward/return dependencies from the compiled topology, configuration/control-plane plans and deployment manifest. Include required access/trunk/VLAN, gateway/SVI/subinterface, transit and route actions without reapplying unrelated configuration. Resolve scope and capabilities before mutation. Reject stale hashes, mismatched subjects, contradictory addresses, dependency gaps, unsupported models and inadmissible required services. Preserve explicit excluded/blocked rows and legitimate retained-result semantics.

**SP1-02 — Operational routed prerequisites.** Establish the intended source/resolver/destination bindings, appropriate L2 forwarding and L3 forward/return forwarding prerequisites before dependent service operations. Readbacks must be fresh, complete enough for the predicate and attributed to exact devices, interfaces, VLANs and prefixes. A configured route, successful setter, aggregate PARTIAL, link-UP flag or green light is not a substitute for its required operational evidence. Check the usable path, not that every redundant STP link is FWD. Wrong next hops, route loops or absent return paths must not yield a positive prerequisite. Passive state establishes prerequisites, not prior packet delivery; the service response is the end-to-end oracle.

Share observations for common dependencies and invalidate them when relevant configuration, identity or routing changes. Preserve established sample/episode/phase distinctions and bounded simulation-progress handling; never regain authority after receiver/ownership loss merely because a later sample looks valid.

**SP1-03 — Cold HTTP by IP.** In the cold acceptance sequence, every selected client's first HTTP-by-IP request precedes any intentional ping, DNS query, traceroute, preliminary HTTP or diagnostic traffic that could warm those paths. Enforce that order through the real product DAG, including upstream verifiers—not a harness-only bypass. Use passive/registered state readers for pre-request prerequisites. No PortFast, link bounce, clock acceleration, arbitrary sleep or extra request may manufacture success. Normal protocol behavior caused by the actual request is permitted.

Retain fresh marker evidence, before-content, selected URL, observed client mode/owner, start result, timing and one finalization outcome per owned client. Sequential clients share infrastructure: do not claim independently cold networks or exact network delivery counts without observation. No automatic retry after an ambiguous request outcome.

**SP1-04 — DNS and hostname composition.** Derive and freshly verify each static client's configured resolver. After cold HTTP, verify a run-specific A record resolves to the expected address through the maintained DNS reader, with qualified positive/negative semantics, then verify fresh HTTP-by-hostname content. Reuse the current reader; S5 is not a prerequisite. A timeout is not NXDOMAIN, a ping response is not HTTP, and a configured DNS address alone is not a demonstrated DNS exchange. Do not overclaim resolver/cache attribution beyond the observation. A failed required DNS prerequisite blocks dependent hostname requests, not an already established by-IP result.

**SP1-05 — Evidence and failure boundaries.** Preserve source SHA/tree, build/channel/session, plans/manifest, declared scope, observations, decisions, first requests, releases and resources. Persist before effects as required and reload the final product record to verify agreement with the public response. Shared contradictions block affected dependents; local failures remain local where safe. Persistence loss, deadline expiry, cancellation and receiver replacement must not permit later ordinary effects or falsely successful completion. Final observations and eligible owned-resource release survive safe failure paths; unresolved ownership stays explicit.

**SP1-06 — Scalability and coexistence.** Derive N clients and topology-dependent groups. Test 2/20/200/1000 clients distributed over valid switch capacities, multiple VLANs and sites through real compilation, orchestration, evaluators and storage with an explicitly substituted external backend. Measure graph/correlation work, engine-call counts, serialized response/record bytes and runtime/memory where relevant. Avoid all-pairs checks, per-client whole-workspace inventories, repeated full route scans and quadratic evidence joins. Build indexes once per fresh shared observation without hiding duplicate/conflicting rows. Finite documented limits are acceptable; silent truncation or a fixed two-PC algorithm is not. Keep existing DHCP, Voice, Printer and local-service regressions intact.

## 5. Verification and LIVE completion

Pair requirements with acceptance, system design with system tests, architecture with integration and module contracts with unit tests. Derive expected results independently of the implementation. Reproduce behavioral defects before causal correction; do not manufacture RED for documentation. Include sequences—not only isolated states: LIS then timely FWD; exhausted sample then valid sample; late FWD; route drift after an earlier positive; local read failure followed by shared contradiction; valid payload for the wrong switch/VLAN; cancellation and persistence failure between effects.

Exercise the registered MCP handler and shared production composition, generated JavaScript under the maintained Node harness where relevant, runtime readers and real record store. For large offline cases substitute only the external boundaries being simulated; returning VERIFIED from a fake does not test the verifier it replaces. Include missing/incorrect return routes, wrong resolver, nonexistent name with a qualified negative, wrong/stale page marker and unsupported shapes. Check both decisions and absence of forbidden calls.

LIVE must demonstrate a representative inter-VLAN/single-gateway workload and a multi-site workload containing at least three routers, with a client-to-service path crossing multiple routing devices. Cover all selected clients in those acceptance workloads, separate DNS/HTTP hosts, cold-by-IP ordering, subsequent DNS/name-based HTTP and useful controlled negatives. Select counts and valid address plans from physical capacity and the phase's requirements; vary addresses and identities rather than hardcode laboratory literals. These are acceptance families, not a fixed number of attempts. Large offline coverage is not native capacity evidence.

Use the maintained deployment and public service route, not manual service configuration or direct private-runtime calls as final acceptance. Controlled qualification may use candidate capabilities; closing SP-1 requires source-backed scoped catalog integration on the feature branch and a successful public route without an unconditional support override. Do not promote unrelated dimensions or call this final independent acceptance.

Run focused and affected checks, proportional broader regressions, namespace inventory, MkDocs, whitespace and clean exact-commit delivery quality gate. Publish by ordinary fast-forward for exact-SHA CI with skip reasons. Final LIVE acceptance must execute a clean published source with its required CI green; exploratory episodes require the applicable offline gates first. Required new acceptance coverage must not silently skip. Preserve failures and intermittent evidence instead of rerunning unchanged suites until green. Bind each LIVE to its executed source; later changes require relevant revalidation or an explicit equivalence analysis, never relabeling an old run.

## 6. Delegated LIVE, autofix and laboratory authority

This is an active grant for SP-1, not a DRAFT. You may make technical decisions within the scope, implement and correct causally, run offline subagents, launch/connect the maintained bridge, create/configure/observe owned labs and run the necessary LIVE experiments. Start with installed Packet Tracer `9.0.1.0858`; bind and record the observed build and a fixed supported channel per episode. Never infer executable version from the reference's export metadata or installation path.

Materialize each episode's exact source, target list, manifest/intent hashes, process incarnation, channel, hypothesis and finite operation/time limits under this work order before effects. Choose and revise future allocations autonomously within actual operator/platform limits. Protect finalization reserves and count nested calls plus local waiting. There is no two-attempt quota; historical ledgers remain consumed and immutable. Do not enlarge an in-flight ceiling retrospectively or repeat an ambiguous mutation. A failed episode ends unsafe effects; reconcile, retire safely, interpret the result and continue with a justified next experiment.

One lead controls LIVE and the shared mailbox; one writer per worktree. Up to three offline subagents may work on disjoint tasks with an integrator. Before effects, verify checkout-local interpreter/import isolation, clean source, exact manifest/model identities, campaign claim and receiver incarnation. Preserve per-dispatch controls and the acknowledged absence of in-band receiver fencing. Use an exclusive disposable lab; any foreign process/document or lost ownership prevents further effects on that subject.

You may save uniquely named lab copies, answer No/Discard on an identified owned save prompt, close and reopen owned instances, and force-terminate only the verified owned process/helper cohort after bounded graceful failure. Preserve evidence first when feasible. Never discard or overwrite user documents, mutate original CP-SCALE/Final-Muejeje labs, or delete foreign mailbox artifacts. Product operations release their own temporary clients; campaign cleanup is separate and must report restoration, backend-managed remnants, retirement and unknowns honestly.

Use official Cisco reference for new API signatures. No unauthenticated endpoint, secret leakage, namespace alias, test weakening or unrelated mass-formatting. No new external expense, credential requirement or expansion into SP-2–SP-5 is delegated. Report a genuinely necessary external intervention precisely; a routine design choice is not a blocker.

## 7. Delivery and mandatory stop

Keep the current brief concise, update maintained architecture/tool/QA projections and preserve historical records. Deliver a single reviewable commit series and an indexed evidence package containing source identities, reference-copy hash/blob, requirements-to-tests/results, public-route LIVE records, counters and timeline, per-client outcomes, negative controls, scale measurements, raw artifacts with verified hashes, cleanup/retirement and precise support limits. Archive the work order with the campaign's grant provenance. The final report must separate measured native behavior, offline simulation, inference and remaining uncertainty.

Declare `READY_FOR_REVIEW` only when SP-1 implementation, required offline checks, exact-SHA CI and public-route LIVE acceptance evidence are complete. Self-review and subagent review do not provide the independent pass. A real external blocker may produce `BLOCKED` with preserved progress and recovery details, never a success claim.

Stop at this phase boundary. Do not begin SP-2, merge to main or create `feature/final-muejeje-non-iot`. After SP-1 receives the independent pass, the user and technical reviewer will activate SP-2; Server-PT integration and the Final-Muejeje implementation branch come only after SP-5 is accepted.
