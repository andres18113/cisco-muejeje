# CP-SCALE 279-endpoint qualification

CP-SCALE qualifies the normal Enterprise product chain at the scale of a
three-site, 279-workload-endpoint network. It is not a separate compiler,
renderer, or runtime path.

```text
EnterpriseIntent -> EnterpriseDesigner -> IPAM / Capacity
                 -> Hardware / Modules -> EnterpriseCompiler / Layout
                 -> typed configuration, control-plane and voice plans
                 -> typed runtime evidence -> cleanup evidence
```

## Current state

The operational authority is
[`reference/cp-scale/current_state.json`](../reference/cp-scale/current_state.json).
This page describes the qualification and keeps its historical record; it does
not govern the state.

CP-SCALE is closed. The `full-qualification` target reached
`CP_SCALE_FULL_QUALIFICATION_VERIFIED_AND_CLEANED`, executed at
`6a80b24626d40fb59bad5f0dc2e47d18a51f4a49`, with the success index
`reference/cp-scale/full_qualification_successful_run.json` pinning its
precleanup evidence, cleanup attestation and final checkpoint. The Router0 and
Router3 branches closed earlier as `ROUTER0_BRANCH_VERIFIED_AND_CLEANED` and
`ROUTER3_BRANCH_VERIFIED_AND_CLEANED`. An earlier full-qualification run failed
at `floor3` when the Packet Tracer process crashed; it stays FAILED and the later
success does not reinterpret it.

The backend qualification policy for Packet Tracer `9.0.1.0858` qualifies voice
configuration, phone registration and extension binding. Call behaviour and
wireless association are unqualified, and intersite calling is off; none of them
is a full-qualification criterion. No re-execution is authorised:
`live_execution_authorized` is `false`, and every canonical target is refused
before Packet Tracer contact unless an explicit authorisation names the target
and the exact source SHA.

## Historical reference inputs

The following documents were admitted as immutable workload snapshots at the
hashes below. Their tracked copies now also record explicitly governed
corrections proven necessary by later runtime evidence; the corrected hashes
are pinned in `handoff.md`. Neither form overrides typed models, catalog
evidence, validation rules, or runtime observations.

| Reference | SHA-256 at admission |
| --- | --- |
| `docs/reference/cp-scale/topologia_completa_IMP.md` | `5ED2374B8496E90B4ED43E7B3D59D7FC42CDB9E1710CD35AA8EC4A7110AA9A0B` |
| `docs/reference/cp-scale/diseno_logico_IMP.md` | `87E729B5504DDA37F8F344034EEAF746AF43E242EA90E9CF6B4093FB2CC01CD0` |

Their fixed workload demand is 279 endpoints. Access points and all derived
switches, routers, modules, and links are infrastructure and are reported
separately. The product scenario preserves exact semantic demand even when a
catalogued generic device must be used for physical realization.

The product's canonical segmentation remains authoritative: DATA 10, VOICE 20,
IoT/CCTV 30, printers 40, wireless corporate 70, and management 99. This is the
typed equivalent of the historical three-VLAN design; no historical defect or
ambiguity is copied silently into generated configuration.

## Claim discipline

Offline compilation can qualify deterministic expansion, addressing, capacity,
physical ownership, coordinates, link validity, configuration coverage, and
semantic hashes. It cannot establish Packet Tracer model identity, wireless
association, live convergence, phone registration, calls, or cleanup behavior.

## Historical: offline qualification checkpoint, 2026-08-20

This section records the offline checkpoint as it stood on 2026-08-20, before the
live closure described under "Current state". Its counts are the evidence of that
run and are not a current measure.

The governed offline run on 2026-08-20 compiled the canonical point D through
the normal designers, planners, compilers, and typed control-plane and voice
use cases. Full generated plans and evidence were written beneath the ignored
`data/cp-scale/offline-full/` directory; only the bounded audit summary is
recorded here.

| Measure | Observed result |
| --- | --- |
| Workload endpoints / access points / network devices | `279 / 17 / 22` |
| Total devices / links / serial WAN links | `318 / 235 / 3` |
| Configuration / control-plane / voice actions | `615 / 164 / 159` |
| Hard layout metrics | zero overlaps, duplicates, out-of-bounds devices, ownership violations, and compactness violations; `100%` valid link endpoints |
| Generic substitutions | `26 webcam`, `42 smoke`, `22 motion`, `2 humiture`, `3 temperature` realized as generic `Thing`, with `exact_model_claim=false` |
| Physical hash | `dbe1cd39a7a192412dd99c2d4743f9514996b51d93126475f63eb931acb918b1` |
| Layout hash | `9b67d11e6bca339649139e53b64607a268238a3d024af23f31c49cc85b9c692e` |
| Artifact hash | `36163ca2d53fc0088c89db6620756ec227ac9b9e008406f9fee74d6ead1b57dc` |
| Configuration hash | `3e5cfcd6f8a5e6c228a3a776850d8ec938b81607a51d42d051071bd331d2d031` |
| Control-plane hash | `080f479bf2eaec96ad2886d6e71a68b434cfb9073339419db01afdabcd705274` |
| Voice hash | `a225fb9ca6fe7e7bb56e2748f19eefe937f706a324ed4123bce8c1d0dd51de20` |

Ten complete offline qualifications produced one stable tuple across all six
hash dimensions. Timing was measured per stage and was not used as a pass/fail
threshold. The full governed repository suite passed at that commit, with the
same four pre-existing warnings; `compileall` also passed.

A generic `Thing` is therefore evidence of a physical substitution, not proof
of an exact sensor class. Exact device models and runtime behavior remain
unknown until registered capability discovery and a fresh typed qualification
run establish them. Webview behavior and exact coordinates after Packet Tracer
transforms also remain backend-limited.

The live progression is monotonic and derived from the same canonical intent:

| Point | Workload scope |
| --- | --- |
| A | First large-branch zone: 65 endpoints plus derived infrastructure |
| B | First two large-branch zones: 118 endpoints plus infrastructure |
| C | Complete large branch: 208 endpoints plus infrastructure |
| D | Complete three-site enterprise: 279 endpoints plus infrastructure |

Every live mutation requires the checkout-local interpreter/import isolation
gate, the current Packet Tracer fingerprint, an empty semantic workspace,
preserved backend-managed devices, and the expected branch/upstream state in
the same process that will mutate. Each point records typed stage results,
fresh observations, bounded convergence, cleanup, and two independent
post-cleanup inventories. A skipped dimension is recorded as zero/not-run; it
is never promoted to supported.

## Historical: read-only live preflight, 2026-08-20

The read-only live preflight on 2026-08-20 could not establish a current
Packet Tracer fingerprint because `GET /ping` on the local bridge timed out.
No mutation was attempted. Point A was therefore recorded as `blocked`; points
B, C, and D and every dependent dimension were explicitly `not_run/0`. The
mechanically verified live workload envelope for that run was `0`, while the
canonical target remained 279. This was an availability result, not evidence
against the offline plans or an inferred Packet Tracer scale ceiling. It has
since been superseded by the closure recorded under "Current state".

## Closure criteria

CP-SCALE closed as `CP_SCALE_FULL_QUALIFICATION_VERIFIED_AND_CLEANED`, recorded
under "Current state" above and pinned by its hash-pinned success index. That
closure, and no earlier formulation, is the authority. Timing is reported but is
not a pass/fail gate: correctness, attributable evidence and a verified cleanup
decide. BGP, IPv6, redistribution, HSRP, E10, and any other scope not already in
the Enterprise chain remain excluded.
