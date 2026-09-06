# Relay prompt: one governed PoE delivery qualification

Copy the prompt below into the next Codex session. This document is a relay,
not semantic authority. Source, tests and direct evidence remain authoritative.

```text
RUN_ONE_NEW_GOVERNED_POE_DELIVERY_QUALIFICATION_WITH_COMPUTER_USE

Repository:
andres18113/cisco-muejeje

Branch:
feature/runtime-ripv2

Publish only to:
cisco HEAD:feature/runtime-ripv2

AUTHORITY

Use:

source + tests + direct evidence
>
docs/reference/cp-scale/current_state.json
>
handoff.md
>
handoff_github_corrections.md
>
history/reports

Never let a handoff override source, tests or direct evidence.

KNOWN PRODUCT STATE

- Productive PoE implementation:
  4c4071923b137d401a4b6b6cb41044c26a295bc1
- Last pushed clean governance HEAD before this relay commit:
  f194ec6bc3302e579c5249b4315567fd2f3e80bf
- GitHub Actions for f194ec6...:
  run 34000154426, 4/4 GREEN.
- The local HEAD at session start should be the documentary commit containing
  this relay. Determine its exact SHA with git; do not invent it.
- That relay commit was intentionally committed locally but not pushed by the
  prior session. Before any LIVE, inspect its complete diff, require a clean
  worktree, push it only to cisco/feature/runtime-ripv2, and require GitHub
  Actions 4/4 GREEN for that exact final SHA.
- current_offline_operational_gate must remain:
  source_head = 4c4071923b137d401a4b6b6cb41044c26a295bc1
  poe_delivery = unknown
  poe_ports = null
  hardware_plan = partially_resolved
  canonical_composition = blocked_before_topology
  router0_authorized = false

LATEST AUTHORITATIVE LIVE

Session poe-e0da8048e559 ran from f194ec6... on Packet Tracer 9.0.1.0858.
Exact scope:

- candidate: 3560-24PS / FastEthernet0/1
- comparison: 2960-24TT / FastEthernet0/1
- candidate endpoint: 7960 / Switch
- comparison endpoint: 7960 / Switch
- one simultaneous binding

Both calls to lwAddLink returned exactly true, used straight-through 8100,
were emitted once each, and produced exact bilateral readback in the first
subsequent readback:

- candidate link id: {735ddb50-1f1c-459c-3f22-098edd4ed4f7}
- comparison link id: {94eba212-1003-3ea5-4922-09c0a59a20c6}

The observation was not delivery evidence. It reported a green link-side
triangle for the candidate and a red link-side triangle for the comparison,
but no unequivocal endpoint-side power signal and no confirmed endpoint
settling. It arrived outside the 300-second deadline. Decision:
C — UNOBSERVABLE / INVALID EVIDENCE.

Cleanup deleted all four temporary identities and semantic restoration was
verified. Power Distribution Device0 is backend-managed; it is not semantic
residue and is not PoE-delivery evidence.

Snapshot:
data/capabilities/runtime/9.0.1.0858/0fa978810e5d4f368126553ce56a767c04c49adc5cb9beac9f04eb52b2494207.json
SHA-256:
98901736ba53266a77d55eb8c54f16be8d0587935f7b9e79e9b23e18fb8eb0f4

LATEST NO-LIVE FACT

After poe-e0da8048e559, an additional LIVE was authorized but not consumed.
Computer Use preflight failed twice, including after a fresh reset:

- apps=[]
- cua.listApps is not a function
- Trusted RPC service is not configured: sky

No qualifier invocation or new snapshot followed those failures.

OBJECTIVE

Execute exactly ONE new governed PoE delivery qualification, but only if
Computer Use can first bind exactly one Packet Tracer native window and take
fresh screenshots. The authorized observer identity is:

Codex-computer-use

Use Computer Use for endpoint-side visual observation so Codex owns and
attributes the observation. If native Computer Use is still unavailable,
stop PRECONDITION_BLOCKED before qualify(); do not fall back to guessing or
consume the LIVE.

PRE-FLIGHT BEFORE ANY PT MUTATION

Verify all of the following in the process that will mutate Packet Tracer:

1. final HEAD equals upstream after the relay commit is pushed;
2. worktree is clean;
3. GitHub Actions is 4/4 GREEN for that exact final HEAD;
4. sys.executable is this worktree's .venv interpreter;
5. packet_tracer_mcp.__file__ resolves inside this worktree;
6. exactly one of packet_tracer_mcp / src.packet_tracer_mcp is loaded;
7. Packet Tracer is exactly 9.0.1.0858;
8. authenticated bridge/MCP Builder is connected;
9. semantic workspace inventory is a complete disposable baseline;
10. Packet Tracer is in realtime mode;
11. current_offline_operational_gate is still PoE UNKNOWN with Router0 false;
12. Computer Use returns exactly one target Packet Tracer window and fresh
    screenshot capture works before qualify().

If any item fails, stop PRECONDITION_BLOCKED. Starting a bridge or performing
read-only inventory/screenshot checks does not consume the LIVE.

LIVE SCOPE

Call the existing product PoEDeliveryQualificationService.qualify() exactly
once with:

- PT build: 9.0.1.0858
- candidate: 3560-24PS
- comparison/control: 2960-24TT
- candidate port: FastEthernet0/1
- comparison port: FastEthernet0/1
- endpoint model: 7960
- endpoint port: Switch
- simultaneous bindings: 1
- observer_id: Codex-computer-use
- method: manual_visible_power_state
- observation window: existing governed 300 seconds

Do not execute Router0.

EXECUTION RULES

- One qualifier invocation only.
- Each arm may call lwAddLink once; never replay it during convergence.
- Require the exact Boolean true result before readback.
- Require subsequent exact bilateral readback for both arms.
- No retry-until-green and no second identical LIVE.
- No arbitrary sleeps.
- Do not modify source during the execution.
- Do not widen bindings or poe_authorized_bindings.
- Do not derive delivery from getPower(), isPowerOn(), link-up, DHCP,
  forwarding, model name, catalog, cable type, or analogy.
- The green/red link triangles observed previously are link-side only and
  cannot establish powered-device delivery.

COMPUTER USE OBSERVATION

Once the fixture and both exact links exist concurrently, use fresh Computer
Use observations inside the deadline. Resolve the exact temporary names from
the returned fixture; never guess them. Inspect the endpoint-side UI/state of
both 7960 endpoints while the same candidate/control fixture remains present.

Record only what screenshots make attributable:

- exact switch/port and endpoint/port identities;
- candidate and comparison endpoint-side visible indicators;
- powered / not_powered / unobservable state for each arm;
- switch_ready, link_ready and endpoint_settled only when actually established;
- simultaneous=true only when both arms belong to the same concurrent fixture
  episode;
- observed_at in UTC and within the existing deadline.

If the phone UI provides no unequivocal endpoint-side power signal, record
UNOBSERVABLE. Do not reinterpret link color as power. Observation through two
independent runs cannot establish simultaneous capacity.

EVALUATION

A — DELIVERY VERIFIED

Only if exact, timely, attributable Computer Use evidence demonstrates the
candidate endpoint powered and the equivalent comparison endpoint not powered,
with all readiness prerequisites and clean restoration. Persist only through
the existing governed snapshot mechanism and authorize no identity beyond the
single observed binding.

B — DELIVERY NOT VERIFIED

Use when authoritative endpoint-side observation is valid but does not show the
required differential. Keep supports_poe UNKNOWN, poe_ports=None and Router0
blocked.

C — UNOBSERVABLE / INVALID EVIDENCE

Use when observation, attribution, deadline, lifecycle or cleanup is incomplete
or ambiguous. Keep everything fail-closed.

CLEANUP

The product service must clean endpoints before switches and verify semantic
inventory restoration. Cleanup/restoration are part of evidence validity. If
they cannot be verified, publish no positive evidence. Stop after this one run
regardless of A/B/C.

POST-RUN

Report only:

RUN_IDENTITY
LIVE_SCOPE
LINK_CONVERGENCE
OBSERVATION
EVIDENCE_AUTHORITY
CLAIM_CEILING
PERSISTENCE
CLEANUP
FINAL_STATE
DECISION
NEXT_ACTIVE_STEP

Include exact HEAD, CI run, PT build, fixture names/bindings, observer,
timestamps/deadline, relevant raw results, link mutation/readback counts,
artifact path/hash and worktree state. Distinguish verified facts, inferences
and pending items.

Even if A, do not execute Router0 inside this task. If B or C, PoE remains
UNKNOWN and Router0 remains blocked.
```
