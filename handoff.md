# Handoff — Stage 3A4

## Current checkpoint

- worktree: `.claude/worktrees/runtime-ripv2`
- branch: `feature/runtime-ripv2`
- implementation HEAD: `5ea2ed3b1d4200430dd918078f1cf4f3cb19746d`
- regression: `1781 passed`
- worktree: clean before this docs-only handoff update; leave clean afterward
- Graphify: current through the offline planning checkpoint

```text
REFERENCE_TOPOLOGY_PRODUCT_PLANNING = READY_OFFLINE
STAGE_3A4 = PARTIAL
TD_ACCEPTANCE_001 = OPEN
E9_5 = OPEN
```

## Offline planning complete

- foundational evidence is derived from executed results rather than asserted;
- serial WAN intent reaches semantic hardware and topology planning;
- `UNKNOWN` and `UNSUPPORTED` remain distinct and fail closed;
- compatible `EDGE_ROUTER + WAN_ROUTER` roles reconcile to one site router;
- the governed reference compiles offline to exactly 41 devices and 41 links;
- E4 accepts only `HardwarePlanStatus.VALID` and preserves mixed causes;
- Graphify covers the final planning route.

Do not reopen offline planning unless executed runtime evidence invalidates one
of these contracts.

## Exact next task

```text
STAGE 3A4 — SERIAL PRODUCT SLICE 2A
MODULE EFFECT EVIDENCE + PRODUCT PHYSICAL DEPLOYMENT
```

Start by recovering the backend's real module observables and strengthening the
existing modular-plan deployment safety gate with typed effect evidence. Never
infer requested `HWIC-2T` identity from successful submission: exact module
identity remains unobservable unless direct runtime evidence proves it.

The first live qualification should eventually be only:

```text
2×2911 + required serial modules + 1 serial WAN
```

Before any mutation, inventory Packet Tracer read-only and hard-stop if any
foreign/manual/graded topology exists. Use disposable exact names, preserve
backend-managed PDD objects, clean up only created resources, and require final
inventory to equal baseline.

Scope limits for Slice 2A:

- no full 41-device reference deployment yet;
- no serial IOS or configuration application yet;
- no RIPv2 orchestration yet;
- no traffic integration yet.
