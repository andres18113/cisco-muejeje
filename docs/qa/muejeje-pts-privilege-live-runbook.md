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
| workspace | not declared, and not recorded | **the two-device fixture below, required before qualification** |
| addresses | typed into the procedure | **read out of the reading that reports them** |
| raw evidence | not captured — the record keeps the operator-reported observations | **one raw transcript, named by the artifact SHA-256, required** |
| everything else | — | unchanged except where governed source and recipe evolution requires |

The right-hand column is **read from the audit, never typed from here**: a
recipe id written into the document that describes the commit it lives in
cannot be correct, and one copied forward from a previous line is worse than
absent. Run the audit, and record what it reports.

The privilege set is the point of the run; the workspace, the observed
addresses and the transcript are what make the run capable of establishing
anything, and none of them changes what is packaged. Everything else differs
only where the governed source and the recipe force it. **The packaged bytes
are not otherwise unchanged**, and saying so would be wrong: besides the
manifest field, the interface page states the privilege the module now
requests, and four engine sources — `060_platform_adapter.js`,
`160_platform_discovery.js`, `170_platform_modules.js` and
`200_runtime_identity.js` — carry corrected comments that used to deny the
privilege the manifest declares. The privilege model also moved into its own
auditor module, a declared tooling input and therefore part of the recipe id. **No
executable V6 behaviour changed**: the comments are comments, and the
dispatcher, the operations, the adapters and every bound are byte-identical in
effect to the artifact already qualified. No capability, transport, link
operation, mutation or M4 work is in this artifact.

## Before packaging

The recipe's four preconditions, and two more that belong to this run:

5. **The manifest declares exactly `["GET_NETWORK_INFO"]`.** A gate holds this,
   so a green suite is the check; it is named here because it is the one field
   the run exists to change.
6. **A disposable workspace holding two devices is open**, prepared by hand
   before the module is started. What it must contain, and the whole of it:

   ```text
   2960-24TT named Switch0
   PC-PT named PC0
   no cable
   no configuration
   not saved
   ```

   **No position is part of the fixture, and none is predicted here.** Where
   either device sits is not something a person places, declares or remembers:
   it is what one reading reports, in that reading (`MJ-002`). A runbook that
   said "Switch0 is at index 0" would be asserting a workspace ordering the
   runtime explicitly refuses to promise, and the first run whose workspace
   disagreed would record our assumption as Packet Tracer's answer.

   **The operator creates it. Muejeje creates, modifies and saves nothing** —
   every admitted operation is read-only, and this fixture is placed by hand so
   that stays true. It is disposable and it is never anyone's real work: no
   saved topology is opened for this run.

### Why an empty workspace would make this run vacuous

`IPC.network()` answering is a fact about the **root**. Everything the
`network.*` readings are for sits below it, and on an empty workspace none of
it is reached: `available_count: 0` is a valid reading that calls nothing
further, so a run over an empty workspace could report a working root while
every member beneath it stayed as unobserved as it was before.

Two devices are what make the descendant members actually run. With the fixture
above in place, a root that answers exercises, where each applies:

```text
Network.getDeviceCount    the inventory has a count to report
Network.getDeviceAt       a device is handed over at each position the count covers
Device.getName            Switch0 and PC0 are named
Device.getModel           2960-24TT and PC-PT are reported
Device.getType            the workspace device type is read
Device.getPortCount       a switch with ports, and a PC, are counted
Device.getPortAt          a port is handed over
Port.getName              that port is named
```

**A member is qualified by its own answer, never by its root's.** If
`IPC.network()` answers and the workspace is empty, no `network.*` member below
it is recorded as observed — the correct record is that the root answered and
the descendants were not reached. That is why the fixture is a precondition and
not a suggestion: without it this run can establish the privilege result and
nothing about the API beneath it.

`platform.*` readings do not depend on the workspace at all — the hardware
factory describes what models exist and instantiates nothing — so the fixture
changes nothing for them, and their members are qualified the same way, each by
its own answer.

## Every address comes from a reading, never from this page

Three of the qualification statements take an address: a `factory_index`, a
`workspace_index`, and a `module_type`. **None of those values is typed from
this document.** Each is read out of the reading that reports it, in this run,
and entered into the next statement — so what the run exercises is what the
target actually offered, and not what a fixture happened to produce once.

The literal values in the recipe's blocks are **placeholders**. They are there
so the statement is a complete, admissible request that a gate can drive
through the kernel; they are replaced before the statement is entered, and a
placeholder entered unchanged makes the answer evidence about a position nobody
observed.

### The workspace chain

1. **`network.device_inventory` runs first** of the three `network.*` readings,
   and its envelope goes into the transcript exactly as it came back.
2. In that envelope, find the entry whose `name` is `Switch0`, and take **the
   `workspace_index` it reports**. That number is the address for the rest of
   the chain.
3. Enter `network.device_identity` with that observed address.
4. Enter `network.device_ports` with **that same observed address**.
5. Both must come back re-reporting the device they were meant to reach:
   `name` `Switch0` and `model` `2960-24TT`. Both operations read the identity
   off the same hand-over they read the rest from, so this is a check the
   answers can actually support.
6. **If the identity they re-report is not that device, the workspace moved
   between observations.** Record `WORKSPACE_ATTRIBUTION_UNSTABLE`, with all
   three envelopes, and **qualify no descendant member**: an address that
   pointed at two different devices in one run cannot attribute any reading
   taken through it.
7. If the inventory reports no entry named `Switch0`, precondition 6 was not
   met. Record that, and qualify no descendant member — the run is a privilege
   result over a workspace this declaration did not describe.

A position is never carried across runs, and never written into this document
as a fact. It is the position the platform handed a device over at, in the one
reading that says so.

### The factory chain

The same rule, one subject over: an index this repository sends is an index the
platform published.

1. **`platform.device_descriptors` runs first** of the three `platform.*`
   readings, bounded by the window the recipe declares, and its envelope goes
   into the transcript as it came back.
2. Take a `factory_index` **that reading actually reported** — the first
   descriptor in the window — and enter `platform.module_descriptors` with it.
   Its answer re-reports `model`, which must equal the `model` the descriptor
   at that index carried.
3. For `platform.module_type_support`, use a `module_type` **the platform
   itself emitted in this run**: a value in that descriptor's
   `supported_module_types`, or the `module_type` of a node in the chassis
   `platform.module_descriptors` just reported. Enter it with the same observed
   `factory_index`.
4. **No module type is taken from this page, from Cisco's documentation or from
   a previous run.** A number chosen that way would make the answer evidence
   about a vocabulary item nobody observed on this target, which is the mirror
   `MJ-014` forbids.
5. If the platform emitted no module type at all in this run — an empty
   `supported_module_types` and a chassis with no module — record
   `platform.module_type_support` as **not exercised**, with the reason.
   Entering an invented number instead would turn a missing observation into a
   fabricated one.

Every request stays inside the bounds the recipe declares. Substituting an
observed address changes *which* subject is read, never how much is read.

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

### The raw transcript — one file, and it is the evidence

**This run produces a single raw evidence file**, written as the run happens
and committed with it:

```text
docs/qa/muejeje-pts-live-transcript-<artifact_sha256>.md
```

**It is named by the artifact, not by the recipe.** A recipe id identifies the
bytes a build *should* produce; the transcript is evidence about the bytes that
were actually loaded, and only the artifact hash names those. Two saves from
one recipe id are two artifacts, and a transcript that could belong to either
attributes to neither.

#### The run header, and it is immutable

The file **opens** with the identity of the run, written once, before the first
statement, and never edited afterwards:

```text
candidate source SHA      the commit the artifact was packaged from
source tree               that commit's tree
build recipe id           report.build_recipe_id, read from the audit
artifact SHA-256          measured outside the artifact, after saving
artifact size             in bytes, measured the same way
Packet Tracer version     the running build
PacketTracer.exe SHA-256  the pinned binary hash, as measured
privilege selection       read back from the module's General tab
Script Engine listing     as Packet Tracer showed it, in its order
workspace precondition    the fixture, as the operator built it
observed device inventory  the network.device_inventory envelope, verbatim
```

The last line is what ties every workspace address in the run to something the
target said. Without it a `workspace_index` in a later statement is a number
with no provenance, and the chain it addresses cannot be read back.

For **every** qualification statement, that file records four things:

| Field | What goes in it |
| --- | --- |
| statement / RID | the exact text entered, and the `operation_rid` it carries |
| returned value | the exact JSON **string** or scalar that came back, character for character |
| Packet Tracer output | exactly what Packet Tracer printed while it ran, or the word `none` |
| module start | which module start — which evaluation — the statement belongs to |

**The transcript is preserved without normalizing or rewriting its envelopes.**
No reformatting, no pretty-printing, no field reordering, no trimming of a long
result, no repair of what looks like a typo. A rewritten envelope is a
paraphrase of the target, and the whole reason this file exists is that the
previous official run kept a summary and could therefore establish no result
shape.

The QA summary in [the offline audit](muejeje-pts-offline.md) interprets the
transcript **afterwards** and cites it. The interpretation is never the
evidence: where the two disagree, the transcript is what happened.

**If something was not captured, the transcript says so** with the word `none`
or an explicit "not captured", in the row it belongs to. Nothing is filled in
from memory, and no envelope is reconstructed (`MJ-011`, `AGENTS.md` rule 6).

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
| a descendant answers | a fact about that `Interface.member`, on the fixture it was asked over, characterized individually |
| a descendant then fails | a fact about that `Interface.member`, characterized individually. It does **not** invalidate the root result |
| a root answers over an empty workspace | the root result, and **nothing** about any member below it — the run did not reach them |
| a descendant re-reports a different device | `WORKSPACE_ATTRIBUTION_UNSTABLE`: the workspace moved between observations, so **no** descendant of that root is qualified |
| a root is still denied | a **contradiction** between the recorded binary evidence and the artifact's behaviour |

**Root privilege qualification and descendant API qualification are separate
verdicts.** If `IPC.network()` answers and a reading below it comes back
`UNAVAILABLE`, record the exact `Interface.member` that was reached, and keep
the two apart: a working root behind a broken descendant is a different state
from a denied root, and merging them would lose both facts.

If descendants return valid observations, characterize them individually —
every descriptor, chassis node and workspace device, verbatim — rather than
promoting one answered call into a capability verdict for the surface. **A
descendant that was never reached is not a descendant that answered**, and the
two-device fixture is what stops "the root answered" from being written down as
if the members beneath it had.

## If a root is still denied

**Do not add privileges.** Not the other eleven tokens the binary carries, not
`IPC` because it reads like the privilege an IPC call would want, and not one
selected mid-run to see what happens. Instead:

1. record the diagnostic verbatim in the transcript, for each denied call;
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
target API from a denial, or from a member the fixture never caused to be
called. It cannot establish anything about a position: an address that answered
in this run is where the platform handed a subject over *in this run*, and
nothing here carries it into the next one. It cannot make the binary map reproducible: `BINARY_MAP_REPRODUCIBILITY`
stays `PENDING` whatever this run returns, because a run tests the conclusion
and never recovers the addresses it was read at.

### Two subjects, and a verdict about one is not a verdict about the other

`OFFICIAL_PACKAGING_PROVED` and `V6_KERNEL_VERIFIED` are `PASS` **about the
artifact at `d37ba37`**, which was packaged, loaded and driven. This candidate
is a different recipe id identifying different bytes, and nothing about it has
been packaged or run. Carrying the first artifact's verdict onto the second is
the mistake this split exists to prevent — it would let a run that never
happened look like one that did.

```text
LAST_QUALIFIED_ARTIFACT (d37ba37)
  OFFICIAL_PACKAGING_PROVED = PASS
  V6_KERNEL_VERIFIED        = PASS

CURRENT_CANDIDATE
  PACKAGED              = PENDING
  V6_LIVE_VERIFIED      = PENDING
  GET_NETWORK_INFO_LIVE = PENDING
```

`M1_CORE_READY = YES` is the milestone state the **previous** governed artifact
established, and it stays exactly where that evidence put it. This run moves no
candidate-specific state until the candidate itself produces the evidence for
it, out of its own transcript.

Expected state going in:

```text
M1_CORE_READY = YES

GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS
BINARY_MAP_REPRODUCIBILITY                = PENDING

CURRENT_CANDIDATE_PACKAGED                = PENDING
CURRENT_CANDIDATE_V6_LIVE_VERIFIED        = PENDING
GET_NETWORK_INFO_LIVE_VERIFIED            = PENDING

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
