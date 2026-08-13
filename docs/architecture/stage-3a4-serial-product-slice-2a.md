# Stage 3A4 — Serial product Slice 2A qualification

- Date: 2026-08-13
- Implementation commit: `e846175b6e2154621e89d24d0809fae0e396d24b`
- Packet Tracer active-file version: `9.0.1.0858`
- Platform: `Windows-11-10.0.26200-SP0`
- Pinned transport: file bridge
- Result: `VERIFIED_CLEAN`

This record covers only the governed physical-product slice:

```text
2×2911 + 2 requested HWIC-2T effects + 1 serial WAN
```

It does not cover the 41-device reference topology, serial IOS, addressing,
configuration application, RIPv2, traffic, CP3, or E9.5 closure. No `.pkt`
file was saved.

## Safety and isolation

The first Packet Tracer operation was a structured, read-only whole-workspace
inventory through `PacketTracerPhysicalTopologyRuntime.observe_workspace`.
The baseline was complete and contained zero semantic devices and zero links.
The active-file version query independently returned `9.0.1.0858`, zero
devices, and zero links before mutation.

The disposable names were exact and unique:

- `MCP-PROBE-S3A4-S2A-20260813T183940Z-R1`
- `MCP-PROBE-S3A4-S2A-20260813T183940Z-R2`

The dedicated qualifier accepts only two 2911s, one requested `HWIC-2T` in
slot `0/0` per router, one serial link between them, and typed disposable
names. It invokes the production deployer/runtime, performs no mutation of its
own, pins one transport, never replays an ambiguous mutation, and cleans exact
attempted names in `finally`.

## Plan and manifest identity

| Field | Observed value |
| --- | --- |
| topology ID | `stage-3a4/slice-2a/20260813T183940Z` |
| deployment ID | `deployment/stage-3a4-slice-2a/20260813T183940Z` |
| physical topology hash | `5eb7d309a85bc8020bda051f0bd94280216d3dbd4c8688a3035973d50f5c9573` |
| environment fingerprint hash | `9bec399fad67c6a54d0f73f22cbf6597cc2adb947108e644b3e67924783f5642` |
| manifest semantic hash | `ce5062ff1ab675e3f3bce45ff25c104d996d7faa64fc097e4571f30d2d4461af` |
| semantic link | `wan/r1-r2` |
| observed endpoints | `r1:Serial0/0/0 ↔ r2:Serial0/0/0` |
| observed runtime link ID | `{a85c5154-00ef-74dd-b2ad-734b9a73dbe9}` |
| serial endpoint orientation | `UNRESOLVED` on both ends |

The manifest link binding was built from fresh two-ended readback, not copied
from the plan. The observed runtime UUID is retained as runtime identity but is
excluded from the semantic hash. The planned interface on each semantic
endpoint must match the observed binding exactly.

## Module effect evidence

Both routers produced the same fresh before/after result:

| Dimension | Before | After |
| --- | --- | --- |
| required serial ports | absent | `Serial0/0/0`, `Serial0/0/1` |
| required port class | absent | `serial` |
| module-tree entry | present but not attributable to requested identity | observed module number `0`, slot type code `18`, port count `3` |
| exact installed module name | not observed | not observed |

The requested insertion slot `0/0` and observed module number `0` are kept as
different fields. This run does not establish that those identifier spaces are
equivalent. The physical effect is verified by the fresh device-port delta,
the encoded `Serial0/0/*` slot namespace, the required port class, and a fresh
module-tree observation. It is not verified by mutation acknowledgement.

The evidence ceiling is therefore:

```text
MODULE_OPERATION_SUPPORT             = SUPPORTED
MODULE_EFFECT_OBSERVATION_SUPPORT    = SUPPORTED
MODULE_EFFECT                        = OBSERVED / VERIFIED
REQUESTED_EXACT_MODULE_IDENTITY      = UNOBSERVABLE / UNVERIFIED
SERIAL_LINK_ENDPOINT_BINDING         = OBSERVED / VERIFIED
SERIAL_CABLE_IDENTITY                = UNOBSERVABLE / UNVERIFIED
PRODUCT_SERIAL_PHYSICAL_DEPLOYMENT   = VERIFIED
```

`APPLIED` and `VERIFIED` remain separate: both module submissions were first
recorded `CHANGED/APPLIED`, then promoted to observed items only after fresh
effect readback. Exact `HWIC-2T` identity was never inferred from the request,
the acknowledgement, the port effect, or the observed module number.

## Cleanup and restoration

Cleanup removed the exact disposable routers in reverse creation order. Both
exact remove operations returned `CHANGED/APPLIED`; no module-removal API was
assumed. A fresh final inventory contained:

- zero semantic devices;
- zero links;
- one Packet Tracer-managed `Power Distribution Device0`, exact model
  `Power Distribution Device`, with zero ports.

Semantic device/link multisets matched the baseline and no pre-existing
backend-managed identity disappeared. `inventory_restored=True`; an additional
independent read-only inventory after the transaction returned the same final
state.

## Runtime debt evidence packet

| Required field | Slice 2A evidence |
| --- | --- |
| exact version and platform | active-file `9.0.1.0858`; `Windows-11-10.0.26200-SP0` |
| exact model/service | two `2911` devices; requested `HWIC-2T` effect in `0/0` |
| slice identity/hash | topology/deployment IDs and physical hash recorded above |
| typed operation/query | `ensure_device`, `ensure_module`, `observe_module_effect`, `ensure_link`, `observe_link`; no IOS/query operation in this physical slice |
| isolation and baseline | disposable transaction; complete inventory with zero semantic devices/links |
| fresh method/window | structured API observations between `18:39:40Z` and `18:39:45Z` in the same pinned file-transport operation |
| controls | positive live effect/readback; offline adversarial controls for absent/partial/stale/wrong-slot effects, malformed observations, wrong identity, and lost acknowledgements |
| observed value | exact port deltas, module-tree fields, device inventories, two-ended link endpoints, and shared UUID recorded above |
| cleanup/post-inventory | two exact remove receipts; final zero semantic devices/links plus one allowed zero-port PDD; restoration `True` |
| evidence reference | this document plus typed `EvidenceRecord`s in the live result |
| final runtime classification | physical effect `VERIFIED`; exact identity `UNOBSERVABLE`; row closure `BACKEND_LIMITATION_CONFIRMED` for exact identity on this backend/model |

## Controls and regression

Focused tests cover empty-workspace ordering, foreign topology hard stops,
malformed inventory, exact PDD classification, multiset restoration, wrong
module slot namespaces, partial/stale effects, absent module-tree evidence,
lost acknowledgements, no replay, cleanup identity mismatch, cleanup unknown,
requested-versus-observed identity separation, wrong manifest interfaces,
reversed link readback, UUID handling, and JavaScript serialization.

The full offline regression after the live run was:

```text
1815 passed, 3 pre-existing pytest deprecation warnings
```

## Governance result

Slice 2A closes the bounded physical/module-effect implementation and live
qualification requested by this stage. It advances the physical, serial, and
authoritative-link-readback rows of `TD-ACCEPTANCE-001`, but it cannot close
that debt: the acceptance criterion requires production configuration,
authentic foundational evidence, typed control plane, and authoritative
query/traffic evidence in the same reference-topology run.

```text
REFERENCE_TOPOLOGY_PRODUCT_PLANNING = READY_OFFLINE
STAGE_3A4                           = PARTIAL
TD_ACCEPTANCE_001                   = OPEN
E9_5                               = OPEN
```

The governed hard stop is after Slice 2A.
