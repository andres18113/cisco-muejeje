# CP-SCALE state and evidence index

Use [current_state.json](current_state.json) for the compact authoritative
phase state. It names the active boundary, the evidence that supports it, and
the small set of keys still projected into `handoff.md` for compatibility.

Supporting records:

- [Router0 failed run bundles](router0_failed_run_bundles.json) canonically
  indexes the three post-ledger executions by complete run identity, executed
  SHA, immutable artifact hashes and verified cleanup. Every entry is
  `FAILED`; publication supplies neither success authority nor Router0 closure.
- [Operator runbook for the one governed observation](ROUTER0_POE_OPERATOR_RUNBOOK.md)
  is the mechanical form of the only remaining step that needs a person:
  which episode to run first and why, the gates the harness enforces, the
  exact receipt the validator accepts, and why both arms powered is a real
  result rather than a failed run. It authorizes nothing new.
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
- [prelive-evidence](prelive-evidence/) contains read-only product admission
  decisions. These are not LIVE attempts; the current Router0 record preserves
  the exact missing PoE bindings, source and snapshot hashes, and the unconsumed
  one-attempt operator authorization. Intended scope is distinct from a compiled
  topology, which the current product refuses to materialize.
- [canonical_voice_runs.json](canonical_voice_runs.json) is the curated Voice
  judgment ledger through its explicit `scope.exhaustive_through` cutoff. It is
  intentionally not an exhaustive attempt counter after that boundary: adding
  a 19-field retrospective judgment would invent provenance.
- `current_state.json#run_accounting` is the attempt-count authority after that
  cutoff. It indexes later runs only from their hash-pinned cleanup archives and
  governed state, and does not manufacture methodology or conclusions.
- [voice_root_cause_implementation_retrospective.md](voice_root_cause_implementation_retrospective.md)
  preserves the causal Voice methodology and closed correction.
- [`handoff.md`](../../../handoff.md) remains historical context and a legacy
  marked-block projection. New phase history belongs in indexed evidence or a
  focused retrospective, not as another long handoff narrative.
