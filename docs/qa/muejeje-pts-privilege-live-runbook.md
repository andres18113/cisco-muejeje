# Muejeje — the minimum-privilege LIVE run

The declaration for the next official manual run. It changes exactly one thing
against the artifact already qualified, and it says in advance what each outcome
would establish — so the verdict is decided before the run rather than argued
after it (`MJ-011`).

**The procedure is not restated here.** It is
[the packaging recipe](muejeje-pts-packaging-recipe.md), followed from step 1.
This page is what makes *this* run identifiable, and the interpretation rules
its results are read under.

## What changes, and what does not

| | Qualified artifact | This run |
| --- | --- | --- |
| source | `d37ba37786107ed8128d17d589d889ee1fe9b16f` | the candidate checked out, read back from `report.source` |
| recipe id | `7d5e710723151a67e2df84dcb11d43b31ad7a89cba8ae2410cdf987689d216bb` | read back from `report.build_recipe_id` |
| artifact | `6951c066ec158d57855dfd739619482cd05f40e007f5c28fb5fcc66e58a12146`, 48185 bytes | measured after saving |
| privileges | `[]` | **`GET_NETWORK_INFO`, and nothing else** |
| everything else | — | unchanged except where governed source and recipe evolution requires |

The right-hand column is **read from the audit, never typed from here**: a
recipe id written into the document that describes the commit it lives in
cannot be correct, and one copied forward from a previous line is worse than
absent. Run the audit, and record what it reports.

The privilege set is the point of the run. Everything else differs only where
the governed source and the recipe force it: the privilege model moved into its
own auditor module, which is a declared tooling input and therefore part of the
recipe id, and the packaged interface page states the privilege the module now
requests. No capability, transport, link operation, mutation or M4 work is in
this artifact.

## Before packaging

The recipe's four preconditions, and one more that belongs to this run:

5. **The manifest declares exactly `["GET_NETWORK_INFO"]`.** A gate holds this,
   so a green suite is the check; it is named here because it is the one field
   the run exists to change.

## The first observation, before any statement is entered

**Confirm on the module itself that only `GET_NETWORK_INFO` is selected**, and
record what the General tab shows. Every other privilege must be unselected.

If more than one privilege is selected, **stop and do not package**. A module
carrying a wider set is a different recipe, and nothing it answered would be
evidence about this one.

## Then the complete read-only qualification

Not the two root calls — **the whole existing qualification**, exactly as the
recipe lists it: `typeof mcpDispatchV6`, identify, capabilities, each of the
five refusal classes, a stop and a start with identify again, and then every
operation `runtime.capabilities` reports, once each.

Record every envelope verbatim, and beside each one whatever Packet Tracer
printed while that statement ran — verbatim, with where it appeared, and
"nothing" when it printed nothing.

The two critical observations are:

```text
IPC.hardwareFactory()   reached by every platform.* reading
IPC.network()           reached by every network.* reading
```

**If they progress beyond the previous privilege denial, continue through all
the platform and network operations in the same run.** The run does not stop at
the roots; the roots are only where its interpretation begins.

## How to read the result

| Observation | What it establishes |
| --- | --- |
| both roots answer | `GET_NETWORK_INFO` is **target-verified as sufficient** for both current root surfaces. `GET_NETWORK_INFO_LIVE_VERIFIED = PASS` |
| a descendant then fails | a fact about that `Interface.member`, characterized individually. It does **not** invalidate the root result |
| a root is still denied | a **contradiction** between the binary evidence and the artifact's behaviour |

**Root privilege qualification and descendant API qualification are separate
verdicts.** If `IPC.network()` answers and a reading below it comes back
`UNAVAILABLE`, record the exact `Interface.member` that was reached, and keep
the two apart: a working root behind a broken descendant is a different state
from a denied root, and merging them would lose both facts.

If descendants return valid observations, characterize them individually —
every descriptor, chassis node and workspace device, verbatim — rather than
promoting one answered call into a capability verdict for the surface.

## If a root is still denied

**Do not add privileges.** Not the other eleven tokens the binary carries, not
`IPC` because it reads like the privilege an IPC call would want, and not one
selected mid-run to see what happens. Instead:

1. record the diagnostic verbatim, for each denied call;
2. finish the rest of the qualification list anyway — a denied reading is still
   a reading, and each statement is entered exactly once;
3. record the contradiction in
   [the privilege map](muejeje-pts-privilege-map.md), beside the binary
   evidence it contradicts;
4. investigate it before any further implementation.

**No privilege is changed mid-artifact.** A module whose privilege set changed
during a run is a different recipe from the one that was packaged, so every
answer after the change belongs to an artifact nobody built.

## What this run cannot establish

It cannot establish that any other call needs `GET_NETWORK_INFO`, or that any
other token is needed by anything. It cannot promote `M2_CORE_READY` or
`M3_CORE_READY` on a root call alone — those need platform readings that
*answer*, and `M3` needs scope that is not written. It cannot baseline the
target API from a denial.

Expected state going in:

```text
OFFICIAL_PACKAGING_PROVED = PASS
V6_KERNEL_VERIFIED        = PASS
M1_CORE_READY             = YES

GET_NETWORK_INFO_BINARY_EVIDENCE = PASS
GET_NETWORK_INFO_LIVE_VERIFIED   = PENDING

M0B_TARGET_API_BASELINED = NOT_COMPLETE
M2_CORE_READY            = NO
M3_CORE_READY            = NO
ZERO_CHANGE_CUTOVER      = NOT_ACHIEVED
```

## Scope freeze

Until this candidate is qualified, none of the following is started: new M3
capability, workspace links, M4, mutations, M7 transport, a compatibility
facade, or a speculative privilege addition. **The next useful information comes
from the target, not from more runtime code.**
