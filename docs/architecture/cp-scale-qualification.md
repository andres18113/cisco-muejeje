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

## Offline qualification checkpoint

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
threshold. The full governed repository suite passed with `2507` tests and the
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

The read-only live preflight on 2026-08-20 could not establish a current
Packet Tracer fingerprint because `GET /ping` on the local bridge timed out.
No mutation was attempted. Point A is therefore recorded as `blocked`; points
B, C, and D and every dependent dimension are explicitly `not_run/0`. The
mechanically verified live workload envelope for this run is `0`, while the
canonical target remains 279. This is an availability result, not evidence
against the offline plans or an inferred Packet Tracer scale ceiling.

## Closure

CP-SCALE closes only as `FULL_TARGET_VERIFIED` or as a mechanically established
lower reliable envelope that leaves the 279-endpoint target intact. Timing is
reported but is not an arbitrary pass/fail gate. Correctness, attributable
evidence, and cleanup dominate. BGP, IPv6, redistribution, HSRP, E10, and any
other scope not already in the Enterprise chain remain excluded.
