# CP-SCALE state and evidence index

Use [current_state.json](current_state.json) for the compact authoritative
operational state. Router0 is closed by the hash-pinned success index executed
at `8980ada7ab993cbe5b5b915cefde24deb04b3e3f`; the closure is valid only with
its cleanup attestation, and no Router0 re-execution is authorized. Router3 has
not been executed, has no acquired LIVE evidence, and is not `VERIFIED`. The
only active next step is governed offline Router3 preparation; no LIVE Router3
execution is authorized yet.

The `historical_pre_router0` section retains the former LIVE state, PoE gates,
authorizations, next steps, and legacy `handoff.md` projection for audit. It is
explicitly non-governing: none of those historical fields authorizes another
Router0 run or controls the current next step.

Supporting records:

- [Router0 successful run](router0_successful_run.json) pins the first governed
  `ROUTER0_BRANCH_VERIFIED_AND_CLEANED` closure, its complete pre-cleanup
  evidence and cleanup attestation. It is the Router0 success authority.
- [Router0 failed run bundles](router0_failed_run_bundles.json) canonically
  indexes the nine post-ledger executions by complete run identity, executed
  SHA, immutable artifact hashes and verified cleanup. Every entry is
  `FAILED`; publication supplies neither success authority nor Router0 closure.
- [Operator runbook for the governed observation](ROUTER0_POE_OPERATOR_RUNBOOK.md)
  preserves the historical mechanical procedure, the gates the harness
  enforced, the exact receipt the validator accepted, and why both arms
  powered was a real result rather than a failed run. It is not a current step
  and authorizes nothing new.
- [The access-point differential, measured, 2026-09-07](POE_ACCESSPOINT_DIFFERENTIAL_20260907.md)
  records the first access-point episode a person actually watched. Both arms
  were OBSERVED powered, so the differential the scope requires was not
  supplied and `supports_poe` stayed UNKNOWN -- not UNSUPPORTED. It also
  enumerates Packet Tracer 9.0.1's complete power API, which is five
  administrative booleans with no endpoint-side inline-power signal to
  substitute, and states the consequence: the 11 `AccessPoint-PT` bindings among
  the 43 the design demands cannot be covered by an endpoint-visible method. It
  names the switch-side alternative -- `show power inline` through the existing
  registered IOS query mechanism -- as the next E5 observable candidate, and
  records that nothing has examined it yet.
- [Factory structure observed, 2026-09-07](ROUTER0_POE_FACTORY_STRUCTURE_20260907.md)
  records why bridge polling was absent, the three read defects that made
  Packet Tracer's own descriptors unreadable, and the resulting measurement:
  `7960` supports `eIpPhonePowerAdapter`, `AccessPoint-PT` supports no
  documented power-adapter type, and both PoE switches are filed under
  `eMultiLayerSwitch`. Factory structure only; it promotes no capability and
  leaves `poe_ports` at 1.
- [Resumed factory diagnosis, 2026-09-06](ROUTER0_POE_RESUME_20260906.md)
  records fresh API review, the exact-model alias fix, and a read-only preflight
  blocked by absent bridge polling before any PT command was sent. Factory
  structure and AP power-source isolation are still unobserved.
- [Operational session handoff, 2026-09-06](ROUTER0_POE_SESSION_HANDOFF_20260906.md)
  is the operator-requested continuation prompt: exact authority, closed PoE
  episodes, human image review, uncommitted factory-diagnostic work and pending
  validation. It is not a new LIVE decision or a claim that Router0 is complete.
- [Later Router0 PoE acquisition episodes and operator images](canonical-live-evidence/poe-acquisition-20260906T211432-df79fafe-diagnostic.json)
  retain the three subsequent closed episodes, exact requests, preflight gates,
  original UNKNOWN results, and cleanup/safety evidence. The latest images show
  both factory AP arms with powered presentation; the operator confirms only
  icon/tab changes. Their late review is diagnostic, not an observer receipt or
  physical-incapability verdict. Independent AP power-source isolation remains
  to be established before another informative qualification.
- [Router0 PoE acquisition episode](canonical-live-evidence/poe-acquisition-20260906T202735-b4810d48-unobservable.json)
  retains the first simultaneous MLS4 fixture: no complete visual receipt,
  no PoE promotion, six owned devices cleaned, Realtime and file/runtime safety
  restored. This is observer failure, not physical impossibility. The bounded
  canvas-layout correction subsequently passed offline/CI gates at `ab2e0f0`;
  later acquisition results are retained separately above.
- [diseno_logico_IMP.md](diseno_logico_IMP.md) and
  [topologia_completa_IMP.md](topologia_completa_IMP.md) preserve the canonical
  design intent.
- [canonical-live-evidence](canonical-live-evidence/) contains immutable LIVE
  archives. Hashes used by the current decision are in `current_state.json`.
- [prelive-evidence](prelive-evidence/) contains historical read-only product
  admission decisions. These are not LIVE attempts; the retained Router0
  record preserves the exact missing PoE bindings, source and snapshot hashes,
  and the then-unconsumed one-attempt operator authorization. That
  authorization is historical and has no present effect.
- [canonical_voice_runs.json](canonical_voice_runs.json) is the curated Voice
  judgment ledger through its explicit `scope.exhaustive_through` cutoff. It is
  intentionally not an exhaustive attempt counter after that boundary: adding
  a 19-field retrospective judgment would invent provenance.
- `current_state.json#historical_pre_router0/live_state/run_accounting` retains
  the attempt accounting after that cutoff. It indexes later failed runs and
  the successful Router0 record through hash-pinned archives without turning
  the historical pre-Router0 gates into current authority.
- [voice_root_cause_implementation_retrospective.md](voice_root_cause_implementation_retrospective.md)
  preserves the causal Voice methodology and closed correction.
- [`handoff.md`](../../../handoff.md) remains historical context and a legacy
  marked-block projection. New phase history belongs in indexed evidence or a
  focused retrospective, not as another long handoff narrative.
