# CP-SCALE state and evidence index

Use [current_state.json](current_state.json) for the compact authoritative
phase state. It names the active boundary, the evidence that supports it, and
the small set of keys still projected into `handoff.md` for compatibility.

Supporting records:

- [diseno_logico_IMP.md](diseno_logico_IMP.md) and
  [topologia_completa_IMP.md](topologia_completa_IMP.md) preserve the canonical
  design intent.
- [canonical-live-evidence](canonical-live-evidence/) contains immutable LIVE
  archives. Hashes used by the current decision are in `current_state.json`.
- [canonical_voice_runs.json](canonical_voice_runs.json) is the indexed Voice
  run ledger.
- [voice_root_cause_implementation_retrospective.md](voice_root_cause_implementation_retrospective.md)
  preserves the causal Voice methodology and closed correction.
- [`handoff.md`](../../../handoff.md) remains historical context and a legacy
  marked-block projection. New phase history belongs in indexed evidence or a
  focused retrospective, not as another long handoff narrative.
