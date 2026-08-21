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

The following documents are immutable workload inputs. They record a historical
Packet Tracer topology and its observed logical design; they are not product
authority and do not override typed models, catalog evidence, validation rules,
or runtime observations.

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
| C | Complete large branch: 217 endpoints plus infrastructure |
| D | Complete three-site enterprise: 279 endpoints plus infrastructure |

Every live mutation requires the checkout-local interpreter/import isolation
gate, the current Packet Tracer fingerprint, an empty semantic workspace,
preserved backend-managed devices, and the expected branch/upstream state in
the same process that will mutate. Each point records typed stage results,
fresh observations, bounded convergence, cleanup, and two independent
post-cleanup inventories. A skipped dimension is recorded as zero/not-run; it
is never promoted to supported.

## Closure

CP-SCALE closes only as `FULL_TARGET_VERIFIED` or as a mechanically established
lower reliable envelope that leaves the 279-endpoint target intact. Timing is
reported but is not an arbitrary pass/fail gate. Correctness, attributable
evidence, and cleanup dominate. BGP, IPv6, redistribution, HSRP, E10, and any
other scope not already in the Enterprise chain remain excluded.
