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
| observed relay inputs | typed into the procedure | **read out of the reading that published them** |
| qualification accounting | every operation entered once | **every operation `EXECUTED` or `NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`** |
| raw evidence | not captured — the record keeps the operator-reported observations | **one append-only transcript per execution, named by artifact SHA-256 and run id** |
| everything else | — | unchanged except where governed source and recipe evolution requires |

The right-hand column is **read from the audit, never typed from here**: a
recipe id written into the document that describes the commit it lives in
cannot be correct, and one copied forward from a previous line is worse than
absent. Run the audit, and record what it reports.

The privilege set is the point of the run; the workspace, the observed relay
inputs, the accounting and the transcript are what make the run capable of
establishing anything, and none of them changes what is packaged. Everything
else differs only where the governed source and the recipe force it.

**The declared artifact inputs differ from the qualified artifact's in more than
the manifest field**, and saying otherwise would be wrong: the interface page
states the privilege the module now requests, and four engine sources —
`060_platform_adapter.js`, `160_platform_discovery.js`,
`170_platform_modules.js` and `200_runtime_identity.js` — carry corrected
comments that used to deny the privilege the manifest declares. The privilege
model also moved into its own auditor module, a declared tooling input and
therefore part of the recipe id. The audit's entry point changed too — it now
compiles the auditor it runs from source, into bytecode of its own, on every
invocation — and it is a declared tooling input as well, so that change moves
the recipe id and touches no artifact input. **No executable V6 behaviour
changed**: every changed engine line is a comment, and the dispatcher, the
operations, the adapters and every bound are unchanged. No capability,
transport, link operation, mutation or M4 work is in this artifact.

**No `.pts` exists for this candidate yet**, so nothing here says what its bytes
are. The saved artifact gets its own SHA-256, measured outside it after saving.
A statement about declared inputs is a statement about what goes into the
build, never about what came out of it.

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

## Every relay input comes from a reading, never from this page

Three qualification statements carry an **observed relay input**: a value one
reading published, sent back by a later statement. The three are not one kind
of thing, and the difference is kept:

| Relay input | What it is | Published by |
| --- | --- | --- |
| `factory_index` | a **factory address** — a position in the factory enumeration | `platform.device_descriptors` |
| `workspace_index` | a **workspace address** — the position one workspace reading handed a device over at | `network.device_inventory` |
| `module_type` | an **opaque platform-produced value** — relayed as the platform emitted it, and never interpreted | `platform.device_descriptors` (`supported_module_types`) or `platform.module_descriptors` (a chassis node's `module_type`) |

The two addresses keep their named domains (`MJ-029`): a factory address is
never sent where a workspace address is expected, and the kernel refuses one
sent the wrong way. **A `module_type` is not an address at all** — it names no
position, and nothing in this run reads a meaning into it (`MJ-014`).

**None of these values is typed from this document.** Each is read out of the
reading that published it, in this run, and relayed into the next statement —
so what the run exercises is what the target offered, not what a fixture
happened to produce once.

The literal values in the recipe's blocks are **placeholders**. They are there
so each statement is a complete, admissible request a gate can drive through
the kernel. **A placeholder is never entered.** A dependent statement is entered
only with the relay input this run observed; one whose input was not observed
is not entered at all, and is accounted for as
`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` (see *Qualification accounting*).

### The workspace chain

1. **`network.device_inventory` runs first** of the three `network.*` readings.
   Its envelope is appended to the transcript body exactly as it came back, and
   that observation is the **provenance anchor** for every workspace address
   used later in the run.
2. In that envelope's bounded window, find the entry whose `name` is `Switch0`,
   and take **the `workspace_index` it reports**. That is the workspace address
   for the rest of the chain.
3. **If the inventory published none** — it did not answer `OBSERVED`, or no
   entry in its window is named `Switch0` — neither dependent statement is
   entered: `network.device_identity` and `network.device_ports` are both
   `NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`, with the reason. No further window
   is requested to look for the device. A workspace with no `Switch0` means
   precondition 6 was not met, and the transcript says so.
4. Otherwise enter `network.device_identity` with that observed workspace
   address.
5. Enter `network.device_ports` with **that same observed workspace address**.
6. Both must come back re-reporting the device they were meant to reach:
   `name` `Switch0` and `model` `2960-24TT`. Both operations read the identity
   off the same hand-over they read the rest from, so this is a check the
   answers can actually support.

A position is never carried across runs, and never written into this document
as a fact. It is the position the platform handed a device over at, in the one
reading that says so.

### What an unstable attribution invalidates, and what it does not

If `network.device_identity` or `network.device_ports` re-reports a device other
than the one the inventory published at that position, record
`WORKSPACE_ATTRIBUTION_UNSTABLE` with all three envelopes. Two different things
are at stake, and the finding is about only one of them:

```text
member/API observation         what one call answered, in the reading that made it
cross-observation continuity   that readings taken through one address describe one device
```

**The finding invalidates continuity, and only continuity.** The cross-reading
`Switch0` chain is not qualified: nothing is concluded about `Switch0` by
joining the inventory, the identity and the ports readings, because the address
did not hold one device across them.

**It does not erase what each call answered.** The inventory's
`Network.getDeviceCount`, `Network.getDeviceAt` and `Device.getName` remain
observations from the inventory. The identity reading's `Device.getName`,
`Device.getModel` and `Device.getType` remain observations of whatever device
that reading was handed, and the ports reading's members likewise. Each member
is characterized from the reading that called it, and a later reading that
found another device at the same position does not unmake an answer that was
given.

### The factory chain

The same rule, one subject over: every factory address sent is one the platform
published, and every `module_type` sent is one the platform emitted.

1. **`platform.device_descriptors` runs first** of the three `platform.*`
   readings, bounded by the window the recipe declares, and its envelope is
   appended to the transcript body as it came back.
2. **Choose the factory address inside that window, preferring evidence.** Take
   the first descriptor in the returned window whose `supported_module_types` is
   non-empty — that choice lets `platform.module_type_support` run on vocabulary
   this target produced. If no descriptor in the window emitted one, take the
   first descriptor in the window. The choice is made among what the reading
   already returned: **no further window is requested to search for a better
   descriptor.**
3. **If the reading published no descriptor** — it did not answer `OBSERVED`,
   or its window is empty — neither dependent statement is entered:
   `platform.module_descriptors` and `platform.module_type_support` are both
   `NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`.
4. Otherwise enter `platform.module_descriptors` with the chosen
   `factory_index`. Its answer re-reports `model`, which must equal the `model`
   the descriptor at that index carried; if it does not, the continuity rule
   above applies to the factory chain exactly as to the workspace one.
5. For `platform.module_type_support`, relay a `module_type` **the platform
   itself emitted in this run**: a value in the chosen descriptor's
   `supported_module_types`, or, when that list was empty, the `module_type` of
   a node in the chassis `platform.module_descriptors` just reported. Enter it
   with the same observed `factory_index`.
6. **No module type is taken from this page, from Cisco's documentation or from
   a previous run.** A value chosen that way would make the answer evidence
   about a vocabulary item nobody observed on this target, which is the mirror
   `MJ-014` forbids.
7. If no `module_type` was emitted at all — the chosen descriptor listed none,
   and the chassis reading yielded no node carrying one —
   `platform.module_type_support` is `NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`.
   It stays that way unless a target-produced `module_type` subsequently exists
   in this run.

Every request stays inside the bounds the recipe declares. Relaying an observed
input changes *which* subject is read, never how much is read, and choosing a
descriptor happens inside the window already returned.

## Qualification accounting

**Every operation `runtime.capabilities` reports receives exactly one status**,
appended to the transcript body at the point it is decided:

```text
EXECUTED                                 entered, and its envelope is in the transcript
NOT_EXERCISED_PREREQUISITE_UNAVAILABLE   a relay input it needs was not published in this run
```

An operation that carries no relay input — every `runtime.*` operation,
`platform.device_descriptors` and `network.device_inventory` — is always
entered, and is always `EXECUTED`. A dependent operation is `EXECUTED` only when
every relay input it carries was observed in this run; otherwise it is
`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`, recorded with the input that was
missing and the observation that did not publish it.

**A placeholder is never entered to satisfy coverage.** Coverage is the
accounting being complete — one status per operation — and not every statement
having been entered. A request carrying a value nobody observed would produce an
envelope that looks like evidence and is about nothing.

**`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` is incomplete target evidence.** It is
not a failure of that operation, not a finding about the platform, and never a
reason to fabricate an input. It says this run did not reach that operation, and
why.

When `platform.device_descriptors` publishes no `factory_index`:

```text
platform.device_descriptors     EXECUTED
platform.module_descriptors     NOT_EXERCISED_PREREQUISITE_UNAVAILABLE
platform.module_type_support    NOT_EXERCISED_PREREQUISITE_UNAVAILABLE
```

When a `factory_index` is published and no `module_type` is emitted:

```text
platform.module_type_support    NOT_EXERCISED_PREREQUISITE_UNAVAILABLE
```

When `network.device_inventory` publishes no `workspace_index` for `Switch0`:

```text
network.device_inventory        EXECUTED
network.device_identity         NOT_EXERCISED_PREREQUISITE_UNAVAILABLE
network.device_ports            NOT_EXERCISED_PREREQUISITE_UNAVAILABLE
```

The accounting is complete when every operation `runtime.capabilities` reported
has exactly one line. An operation with no line is a gap in the run's record,
not a status.

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
operation `runtime.capabilities` reports, each accounted for as above.

Record every envelope verbatim, and beside each one whatever Packet Tracer
printed while that statement ran — verbatim, with where it appeared, and `none`
when it printed nothing.

### The raw transcript — one per execution, and it is the evidence

**Each execution of the run produces its own raw evidence file**, written as the
run happens and committed with it:

```text
docs/qa/muejeje-pts-live-transcript-<artifact_sha256>-<run_id>.md
```

**Artifact identity and run identity are different, and the name carries
both.** The artifact SHA-256 names the bytes that were loaded; a recipe id names
only the bytes a build *should* produce, so it cannot stand in. The `run_id`
names this execution: the same artifact run twice is two runs, and the second
must never overwrite, extend or be merged into the first. Neither the recipe id
nor the artifact hash alone identifies an execution.

**`run_id` is created before qualification begins**: the UTC time the run
starts, written `YYYYMMDDTHHMMSSZ`, and recorded in the header. If a transcript
with that name already exists, the `run_id` is wrong — take a new one. Another
run's file is never opened for writing.

#### The pre-run header, and it is immutable

The file **opens** with facts that exist before the first qualification
statement is entered, written once and never edited afterwards:

```text
run_id                    created before qualification begins
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
```

**Nothing a qualification statement observes belongs in the header.** A header
that needed an answer would have to be written after the run it is meant to
precede, and could then no longer be immutable. Every field above is known
before `typeof mcpDispatchV6` is entered.

#### The body, and it is append-only

After the header, the transcript is **chronological and append-only for the
whole run**: each statement and its answer are added as they happen, each
accounting status as it is decided, and nothing already written is edited,
reordered or removed.

**The `network.device_inventory` observation lives in the body**, at the point
it was taken, like every other answer. It is the provenance anchor for every
later workspace address: a statement that relays a `workspace_index` names the
inventory observation it was read out of, by `operation_rid`. Without that
anchor a `workspace_index` in a later statement is a number with no provenance,
and the chain it addresses cannot be read back.

For **every** statement entered, the body records five things:

| Field | What goes in it |
| --- | --- |
| statement / RID | the exact text entered, and the `operation_rid` it carries |
| relay input | each observed relay input the statement carries, with the `operation_rid` of the observation it was read out of — or the word `none` |
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
the platform and network operations in the same run**, each accounted for as
above. The run does not stop at the roots; the roots are only where its
interpretation begins.

## How to read the result

| Observation | What it establishes |
| --- | --- |
| both roots answer | `GET_NETWORK_INFO` is **target-verified as sufficient** for both current root surfaces. `GET_NETWORK_INFO_LIVE_VERIFIED = PASS` |
| a descendant answers | a fact about that `Interface.member`, on the fixture it was asked over, characterized individually |
| a descendant then fails | a fact about that `Interface.member`, characterized individually. It does **not** invalidate the root result |
| a root answers over an empty workspace | the root result, and **nothing** about any member below it — the run did not reach them |
| a dependent operation's relay input was not published | `NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`: incomplete target evidence for that operation — neither its failure nor a platform finding |
| a descendant re-reports a different device | `WORKSPACE_ATTRIBUTION_UNSTABLE`: the cross-reading chain is **not** qualified, and each call's own answer still stands in the reading that made it |
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
2. finish the rest of the qualification anyway — a denied reading is still a
   reading — and account for every operation: one whose relay input the denied
   reading could not publish is `NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` and is
   not entered with a placeholder, and none is entered twice;
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
called. It cannot establish anything about a position: a factory or workspace
address that answered in this run is where the platform handed a subject over
*in this run*, and nothing here carries it into the next one. It cannot turn
`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` into anything but incomplete evidence
for that operation. It cannot make the binary map reproducible:
`BINARY_MAP_REPRODUCIBILITY` stays `PENDING` whatever this run returns, because a
run tests the conclusion and never recovers the functions and offsets it was
read at.

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
