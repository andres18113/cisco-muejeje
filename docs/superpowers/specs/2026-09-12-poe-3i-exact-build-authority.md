# POE-3I Exact-Build Factory Authority

## Scope

This decision applies only to Packet Tracer `9.0.1.0858`, device model
`3650-24PS`, required module `AC-POWER-SUPPLY`, module type `4`, and the
factory-preparation mutation owned by this runtime. It does not establish an
occupancy rule for another model, build, module, or arbitrary use of
`getModuleAt(i)`.

## Authority decision

`ModulePhysicalView` remains captured in full but is `DIAGNOSTIC_ONLY`. Its
`module_added` value cannot create `EMPTY`, `OCCUPIED`, or `CONTRADICTORY`, and
cannot veto installation. For a fresh-owned 3650 with no ambiguous prior
mutation, the exact policy and official model semantics establish initially
empty compatible PSU bays. The minimum compatible index is selected by
production; the caller supplies no target.

The measured factory mutation contract establishes one narrow indexed delta:
before, `getModuleAt(4)` is null; one
`addModuleAt("AC-POWER-SUPPLY", 4)` returns true; after,
`getModuleAt(4).getDescriptor().getModel()` is exactly
`AC-POWER-SUPPLY`, while entries 0, 1, 2, 3, and 5 do not change.

## Verification

Structural PASS requires all of the following:

- exact model/build/policy and fresh-owned authority;
- supported inventory contains `AC-POWER-SUPPLY`;
- slot types expose compatible type-4 indexes and policy requires one PSU;
- no ambiguous or competing mutation;
- `native_ack is True` and the reported target exactly equals the selected
  target;
- target identity is observable and exactly `AC-POWER-SUPPLY` after mutation;
- non-target indexed entries, container navigation, and slot structure do not
  drift.

A different or unobservable post identity fails closed. A false PhysicalView
after an otherwise exact indexed delta is recorded as
`diagnostic_inconsistent_with_runtime=True`, not as an authority
contradiction. A non-fresh-owned device does not receive the governed initial
empty-state assumption and remains fail-closed.

Structural preparation is not PoE qualification. The runner must additionally
observe `Available 0.0 W` before and `Available 390.0 W` after the structural
PASS before it creates phones.

## Maintainability

The existing test support/AST guard and the 1601-line legacy-test ratchet are
accepted as POE-3I/6. New semantic cases live in
`tests/test_factory_module_occupancy_authority.py`. Python occupancy authority
and post-mutation verification move out of `factory_module_runtime.py` into
focused modules after GREEN. A file-specific LOC ratchet prevents that runtime
hotspot from growing back; no project-wide LOC limit is introduced.

## Live progression

After focused, affected, full, diff, graphify, push, and exact-SHA 4/4 CI gates,
run the governed 3650 LIVE B on `Gi1/0/{2,3,5,6,7,8,9,10,11,12,13}` with
`AUTO_1 -> NEVER -> AUTO_2 -> RESTORE`. Admission requires 11/11, 0/11, and
11/11 respectively plus complete restoration. Only a positive real A+B product
admission may advance to Router0 offline hash/equivalence checks and Router0
CP-LIVE. Router3 is out of scope.
