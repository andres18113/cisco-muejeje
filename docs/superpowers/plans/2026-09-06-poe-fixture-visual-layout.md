# PoE fixture visual layout implementation plan

> **For agentic workers:** Execute this bounded task inline; obtain a fresh read-only code review before commit. The operator has authorized autofix and continuation, not a planning-only handoff.

**Goal:** Make simultaneous PoE fixtures individually accessible to the visible observer without the modal Workspace List.

**Architecture:** Change only temporary-device canvas positions in `PacketTracerPoEDeliveryFixtureRuntime`. Reserve deterministic grid positions per creation attempt; keep exact names, models, ports, one-shot mutations, bilateral readback, observation and cleanup contracts unchanged.

**Tech Stack:** Python, pytest, existing PTBuilder `lwAddDevice` generator contract.

**Spec:** Operator request `ACQUIRE_ROUTER0_POE_EVIDENCE_THEN_RUN_ROUTER0`; direct episode `r0poe-mls4-b4810d48` retained under `tmp/router0-poe-live/`.

## Global constraints

- No PoE promotion from layout, link state or administrative power fields.
- No increased observation deadline, late receipt, or retry-until-green.
- Local `.venv`, production import isolation, exact clean SHA and Actions 4/4 before further LIVE.
- No Router3; preserve historical Floors/PVST/Voice and existing exact Fa0/1 evidence.

## Task: Replace coincident fixture positions

**Files:** `src/packet_tracer_mcp/infrastructure/execution/poe_delivery_runtime.py`, `tests/test_poe_delivery_runtime.py`.

**Interface:** Existing `create_device(model, temporary_name, required_ports)` remains unchanged. Position is presentation-only, not binding authority.

- [x] Add a causal test that creates 50 temporary devices through the real generator and extracts every `lwAddDevice` coordinate pair. Require 50 distinct positive pairs below PT's directly observed clamp of 3899/3900, and exactly one dispatch per device.
- [x] Run the focused causal test; verify RED on coincident positions (1 unique pair, 50 required).
- [x] Initialize an attempt ordinal in the runtime. Generate `(160 + 320 * (ordinal % 4), 160 + 140 * (ordinal // 4))`, increment before dispatch, encode each number with `json.dumps`, and pass those literals to the existing `lwAddDevice` call.
- [x] Run focused PoE/runtime/safety tests, affected compiler/governance/isolation checks, then full local pytest; run `graphify update .` and `git diff --check`.
- [ ] Obtain fresh read-only review; fix actionable findings, stage exact paths, commit and push only `cisco/feature/runtime-ripv2`; require exact-SHA Actions 4/4.
- [ ] Resume the governed qualification with this causal presentation change. Inspect candidate and control endpoints from canvas, close UI modals before returning the receipt, and persist the governed result. Layout success alone is not a positive PoE result.

The first episode produced no complete receipt, so its capability is UNKNOWN. It cleaned six owned devices, restored the semantic inventory and Realtime, passed file/runtime safety and persisted. The initial phone GUI warning is retained, but does not establish switch readiness or a physical limitation.

## Offline evidence

- Causal RED: old generator produced one repeated `(9000, 9000)` coordinate for all 50 creations.
- Focused PoE/safety: 135 passed. Added timeout-then-success position reservation coverage after review.
- Final affected governance/runtime/isolation: 88 passed.
- Final full suite: 3804 passed, four pre-existing warnings, 214.51 seconds. JUnit retained at `tmp/poe-layout-full-governance-final.xml`.
- Production import preflight: local `.venv`, package inside this checkout, only `packet_tracer_mcp` loaded.
- Fresh independent source and governance review: no remaining actionable findings. Active labels distinguish prior positive evidence from the latest UNKNOWN acquisition.
- No positive PoE or live canvas-accessibility claim follows from these offline checks.
