# POE-3B: productive multi-port PoE authority foundation

## Decision and scope

POE-3B adds the offline contracts needed for one future governed LIVE
qualification to authorize several exact PoE bindings observed simultaneously.
It does not execute Packet Tracer, acquire evidence, create a `.pts`, change the
CP-SCALE topology, or run Router0.

The integration prerequisite is `feature/runtime-ripv2` fast-forwarded from
`62db3cea84a4bfca1a5bcd3d2389d62864c45946` to
`e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43`. The latter is a descendant with
zero feature-exclusive commits and passed the four-job exact-SHA workflow in
run `34406715088` before POE-3B implementation began.

## Authority boundaries

Manual visible delivery and PSE delivery remain independent evidence bases.
Neither can borrow fields from the other. Both converge only at
`PoEAuthorizedClaim`, and the existing claim ceiling remains exact by switch
model, Packet Tracer build, switch port, endpoint model, and endpoint port.

Schema 2 remains the historical single-port PSE contract. Its constants,
dimension set, encoder, decoder and interpretation are not widened. POE-3B
defines schema 3 in a separate module. A schema 2 record continues to authorize
one binding and a simultaneous count of one exactly as before.

Independent runs may never have their simultaneous counts added. The resolver
continues to publish the largest valid single-run count and the exact bindings
actually admitted by decoded claims.

## LIVE session safety modes

`LiveSessionSafetyMode` has two values:

- `GUARDED_PTS_COPY`: the existing `LiveSessionSafetyEvidence`, existing
  path/hash rules and historical serialization. Its mode is exposed as a typed
  property so old snapshots gain no new serialized field.
- `EPHEMERAL_UNTITLED_WORKSPACE`: a sibling typed evidence model with no `.pts`
  path or hash fields.

An ephemeral positive admission requires all of these raw facts:

1. Initial and final semantic workspaces contain zero devices and zero links.
2. `saved_filename` is exactly empty before and after.
3. The session-owned Packet Tracer workspace-file ledger explicitly records
   policy, attempts, denials, callback invocation, observed completion and
   indeterminate results; every collection is present and empty.
4. Initial and final inventory fingerprints are present, exact non-blank
   identities in the existing semantic format, and equal.
5. The fixture is completely removed.
6. Simulation mode is Realtime before and after.
7. Exactly one positive Packet Tracer PID is observed before and after, and it
   is the same PID.
8. File-bridge heartbeat is healthy and mailbox entry tuples are explicitly
   empty before and after.
9. Branch, source HEAD and source tree are exact and unchanged; the worktree is
   clean before and after.
10. Runtime health is true, crash detection is false, integrity/reuse/admission
    conclusions are true, and failure reasons are empty.

Missing, malformed, contradictory or merely truthy values fail closed. The
validator dispatches by evidence type; guarded-path validation remains intact.

## PSE schema 3

Schema 3 carries a closed dimension set containing:

- evidence kind and schema version;
- exact switch model and Packet Tracer build;
- observer, qualification/experiment identity and UTC observation time;
- one ordered, non-empty, duplicate-free tuple of `PoEAuthorizedBinding`;
- exactly three captures in `AUTO_1`, `NEVER`, `AUTO_2` order;
- for every capture, exactly one state for every declared binding in the same
  order, with no missing, duplicate or extra binding;
- the complete existing PSE gate set;
- clean cleanup and restored inventory;
- `simultaneous_active_ports`.

Every AUTO capture must show every binding present, operationally `on`, drawing
positive wattage and delivering. NEVER must show every binding either absent
or explicitly off at zero wattage, with none delivering. The simultaneous
count equals the number of bindings and the enclosing capability result's
`observed_value` exactly.

Re-encoding must reproduce every schema 3 dimension byte-for-value. Unknown or
missing dimensions fail closed. A valid decoder returns only the declared
bindings; it cannot extrapolate to a different port, endpoint, model or build.

## Governed qualification plan

The canonical plan is derived at runtime from `cp_scale_intent()`,
`cp_scale_physical_design()` and the existing canonical stage-inclusion policy.
It joins expanded endpoints whose `requires_poe` is true to their exact
physical bindings, groups them by the selected switch model, removes only exact
duplicate triples while preserving governed order, and sets simultaneity to
the resulting binding count. `AccessPoint-PT` remains excluded because the E4
endpoint truth marks it externally powered.

For target `router0-branch` and build `9.0.1.0858`, the result is:

- `3560-24PS`: `7960/Switch` on `FastEthernet0/1..21`, simultaneous 21.
- `3650-24PS`: `7960/Switch` on
  `GigabitEthernet1/0/{2,3,5,6,7,8,9,10,11,12,13}`, simultaneous 11.

The 3560 scope covers MLS5 and Switch3 by exact subset. The 3650 scope covers
MLS3 and MLS4 by exact subset. This is subset coverage of measured triples,
not extrapolation.

## Runner

`tools/poe3a_pse_live.py` remains the single PSE capacity qualification runner
and is generalized instead of copied. The caller must provide `--model` and a
safe `--qualification-id`; no binding, IOS or JavaScript argument exists.
Effective bindings come only from the governed Router0 plan.

The runner creates one switch and one phone per binding, applies only the typed
`AUTO -> NEVER -> AUTO` mechanism to all governed ports, observes all ports in
each stable capture, cleans every created identity, constructs ephemeral safety
from acquired facts, and produces schema 3. A positive runtime snapshot may be
persisted only after the schema decoder and LIVE safety validator both accept
the completed run. Persistence happens after cleanup and does not count as a
Packet Tracer workspace save.

The runner reaches Packet Tracer only through `PacketTracerPoE3BSession`. The
session privately composes the existing IPC, fixture, IOS and observer runtimes;
the runner has no raw JavaScript or generic transport surface. Its EPHEMERAL
workspace-file policy is empty, and any attempted, denied, invoked, completed or
indeterminate workspace-file operation blocks positive admission.

The historical POE-3A evidence bundle and all prior snapshots remain unchanged.

## Offline acceptance

Tests must establish schema 2 compatibility; valid and invalid schema 3;
missing, duplicate and extra bindings; a single non-delivering AUTO row;
incomplete NEVER; wrong simultaneity/observed value; incomplete ephemeral
safety; no capacity sum across runs; exact plan contents/subset coverage; A-only
3560 admission; and A+B canonical Router0 materialization with current E4, E5,
E9 and Voice hashes and source-hash relationships.

Synthetic contract fixtures are test-only. They may make the offline product
composition valid, but they never enter the real store and grant no LIVE
authority.

## Completion boundary

Focused, affected and full tests, diff review, Graphify update, exact-SHA push
and four-job CI are required. The worktree must finish clean. The next LIVE
action, only after this offline delivery is approved, is A:
`3560-24PS / 21 x 7960`, followed by an audit before B.
