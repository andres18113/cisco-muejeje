# Server-PT IOS observation fast loop, version 1

## Problem and outcome

The second complete C31 attempt, `e0a7dfe16198cb14809fd78dcbb8003a`, selected
30 clients and dispatched no HTTP request because the product readiness gate
refused both access groups. The operator's work order
(`ServerPT_Autonomous_LIVE_FastLoop.md`, SHA-256
`3ed40bd1e3bfc433f340c995d3e5944b010e3099e8e1e1228953d2304646a793`) opens a
new campaign, `SERVER-PT-IOS-FASTLOOP-01`, to repair the actual IOS observation
boundary and demonstrate 30 fresh HTTP-by-IP markers through the maintained
scalable product path. It also replaces the C31 testing cadence with an
explicit experimental LIVE purpose. Risk is **L**: the change touches
authorization, evidence, persistence and LIVE execution. The two C31 attempts
remain consumed and unchanged.

## Diagnosis from the originals

All 301 files in the C31 index verified against their recorded SHA-256 and
size before use. The acceptance journal of the second attempt holds 228
dispatches. Two readiness episodes ran, one per access switch:

| Group | Samples | Channel calls | End | Last failure |
| --- | --- | --- | --- | --- |
| `HQ-DEFAULT-ACCESS-SW-02`, VLAN 10 | 11 | 61 | deadline | `IOS session state: failed`, `sample_after_deadline` |
| `HQ-DEFAULT-ACCESS-SW-01`, VLAN 10 | 10 | 60 | deadline | `sample_call_budget_exhausted` |

The earliest failed boundary is the per-sample nested-call limit, not the
network. `READINESS_SAMPLE_CALLS = 6` was derived from an engine stub where
"one `show spanning-tree` sample is four calls" and never paginates. On build
`9.0.1.0858` a 2950T-24 with VLAN 1 and VLAN 10 prints two pages: page one is
27 content lines (1045 bytes) and stops inside the `VLAN0010` header on both
switches; page two was 17 lines (7 access rows) on SW-02 and 34 lines (24
access rows) on SW-01. `ControlledIosExecutor` needs, for a clean two-page
read: state read, guarded dispatch, output poll, attribution read, capture
session read, continuation key, progress read -- seven calls. With six, the
continuation key is always the last permitted call; the capture then fails,
the pager cancellation is refused by the exhausted channel and the session is
quarantined. Every later sample spends its first calls on isolation (state
read, Ctrl-C, confirming read, re-read) and runs out right after the new
`--More--`. The loop never completes a sample (journal sequences 108-228).

The native answers settle the network question. At sequence 114 (30.6 s into
acceptance, one call after SW-02's first sample was spent) the completed
table shows every requested SW-02 access port `LRN`: ordinary STP learning
after the access VLAN assignments dispatched at 10.9 s. At sequence 175
(62.4 s) SW-01's completed table shows all 24 requested access ports `FWD`.
The observer could not read an answer that already existed. SW-02's final
label is a consequence: its eleventh sample started 0.06 s before the 30 s
window closed, the state read was dispatched with that remainder, returned no
answer after 1.6 s of mailbox cancellation, and `_prepare_session` reports an
unanswered read as `failed`. The trunk tables read during setup are single
pages (four calls). The A10 static-endpoint correction is not implicated and
remains unchanged.

## Scope and exclusions

In scope: the readiness sample composition and its cost model; an explicit
execution purpose in the existing commissioning grant machinery; a persistent
campaign ledger with episode records; accurate forced-retirement evidence for
an owned disposable process; the regressions for all of these; experimental
LIVE episodes under the new campaign; and final delivery verification.

Out of scope: planners, parsers, transports or a second service engine; the
public service tool signature; routed services, mail, DHCP allocation,
wireless, new `.pts`, PortFast, port bounce, ping, DNS verification or extra
HTTP warm-up; C31 history, grants and its two-attempt limit; capability
promotion; merge or force-push. The diagnostic D-WEB and Voice observers keep
their declared six-call samples: they are separate budgeted contracts, and the
same blindness on paginated tables is recorded here as a limitation rather
than changed silently.

## Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| F1 | Execution purpose is explicit and closed | Every campaign grant, seal and status names `delivery` or `experimental`; the C31 campaign is delivery and FASTLOOP experimental; unit tests derive both |
| F2 | Delivery keeps its controls | A delivery grant or seal still refuses a dirty, unpublished or CI-less source and a CI run for another SHA; existing C31 tests stay green unchanged in meaning |
| F3 | Experimental authority needs a frozen local checkpoint, not CI | Experimental preflight refuses a dirty tree, missing tree, wrong branch, failed import isolation or any supplied CI claim; it accepts a clean local commit ahead of its upstream and records the upstream separately |
| F4 | Experimental authority cannot leak | An experimental grant fails a delivery re-derivation and vice versa; a delivery seal refuses an experimental setup grant; an experimental acceptance never reports `accepted` |
| F5 | Campaign consumption is cumulative and protected | 50,000 operations and 21,600 s total; ordinary allocations leave 1,000 operations and 600 s untouched; only cleanup/retirement may use them; an unclosed episode is charged conservatively; a new process recomputes the same totals from write-once files |
| F6 | Each episode is declared before contact | Question, source SHA/tree/upstream, tests run, targets, effects, finite allocation and stop rule are written once before any phase; a phase without an open episode, or beyond its allocation, is refused before a mailbox exists |
| F7 | One readiness sample can finish a real paginated read | Replaying the original SW-01 answers through the real executor and runtime observer reproduces the original refusal at six calls and completes an authoritative sample at the new ceiling; a session left with an active pager still completes; a read needing more calls than the ceiling fails closed |
| F8 | Approved costs stay true | Each readiness episode's enforced call allowance equals the allowance every cost model already names (181 access, 6 per continuity reading); the legacy 1,015 and scalable 7,849 ceilings, and the MCP/acceptance same-product contract (C11), hold unchanged |
| F9 | Retirement is accurate | Exit evidence distinguishes graceful `exited` from `exited_forced`; forcing requires the owned launch identity rechecked, the cleanup archived as restored and an independent census of zero processes; delivery accepts only graceful exit |
| F10 | LIVE product proof | From a fresh campus, all 30 clients appear, each with admissible readiness before its request, a fresh marker by IP, accounted release, valid publication, reloadable records and observed cleanup/retirement |

## Design

**Execution purpose.** `ServerPtCampaign` names a campaign's identity,
charter digest, purpose, deployment and authorization prefixes, attempt limit
and any pinned acceptance cost. C31 is `delivery`, limit 2, pin 7849/2792.
FASTLOOP is `experimental`, no attempt limit (the ledger bounds it), no pin.
One rule, `source_authority_findings`, decides source admissibility for both:
delivery requires the clean published HEAD and exact-SHA CI; experimental
requires a clean committed checkpoint and refuses any CI object, so an
ancestor's CI can never be relabelled. The grant, preflight, seal, store and
CLI take the campaign explicitly; the default stays C31, so no existing call
changes meaning. Grants carry `execution_purpose` and the observed upstream.
Re-derivation uses the caller's campaign, which is why a grant from one purpose
never re-derives under the other.

**Ledger and episodes.** Under `data/commissioning/SERVER-PT-IOS-FASTLOOP-01/
ledger/` write-once files record episode openings, phase admissions, phase
results and closings. Totals are recomputed from them on every decision.
Closed episodes charge their recorded operations and active seconds; an open
episode charges its whole operation allocation and the larger of its seconds
allocation and its elapsed time; a phase admitted without a result charges
its grant maximum. Opening requires the allocation to fit the ordinary
remainder. A phase must fit its episode's remaining allocation, except that
cleanup may draw the protected reserve. The ledger never resets and never
subtracts.

**Readiness sample composition.** `registered_read_call_ceiling(pages)` in the
executor module names each call of one registered paginated read: session
state read and isolation of a leftover pager (Ctrl-C, confirming read plus one
slack read, re-read), dispatch, output poll plus one slack read, attribution,
and for a paginated table a capture session read plus, per continuation page,
a key, a progress read and one slack read. That is `9` calls for one page and
`10 + 3 * (pages - 1)` otherwise. The gate uses a page allowance of 3 (two
measured pages plus one of headroom), so one sample may spend
`READINESS_SAMPLE_CALLS = 16`. The allowance bounds the worst case with slack;
it is not a page limit.

What was wrong was the split of an episode's calls, not their total. Every
cost model, the legacy two-client proposal (1,015) and the scalable C31 scope
(7,849) were computed with an access episode of `30 * 6 + 1 = 181` calls and a
continuity episode of six calls per switch reading per round. Those totals
are now enforced as `episode_calls` by the runtime: each sample borrows up to
sixteen from the episode, no sample starts when nothing is left, and a sample
granted less than a whole read ends `sample_call_budget_exhausted`, never
admitted. A normal episode spends about seven to ten calls per sample, so the
approved totals are ample, and no ceiling, grant or pin changes. A per-profile
ceiling was rejected: it would have made the legacy acceptance measure a
different product than the MCP tool, breaking the same-product contract C11.
The MCP tool and every acceptance profile run the same gate. The diagnostic
D-WEB and Voice observers call the runtime without an episode allowance and
keep their six-call samples.

**Retirement.** `CloseMainWindow` is requested first. If the owned process has
not exited within a bounded wait, the capture may record an exact-PID
termination only after the cleanup is archived as restored, the launch PID,
path and creation time are rechecked, and the workspace is the declared
disposable document. `--record-exit` independently observes zero processes and
records `exited_forced`; it is never rewritten to `exited`.

## Invariants

No effect precedes admission, episode opening, sealed grants and exact
receiver identity. Delivery semantics do not weaken. Experimental authority is
selected only by campaign identity plus its charter digest, never by a flag.
Historical evidence is immutable. A lost mutation response is never replayed.
An exhausted, late or unattributed sample authorizes nothing. No source edit
occurs while a checkpoint's runtime is active.

## Test design

Unit: campaign policy and source rules (F1-F4), ledger arithmetic and
persistence (F5-F6), call ceiling composition (F7), cost pins (F8) and exit
evidence (F9). Integration: the original acceptance answers replayed through
`ControlledIosExecutor` and `observe_access_forwarding` (the original refusal
at six calls, an authoritative admission at sixteen, a leftover pager
isolated inside one sample, the LRN switch still refused, fail-closed when a
read needs more calls than the ceiling, and the episode allowance bounding
all samples together), the gate passing both bounds, both acceptance
profiles recording the ceiling they ran, and CLI experimental phases with
injected readers. System and
acceptance: LIVE episodes (F10), reported with their original chronology.
Verification per change is focused plus affected tests and targeted
Ruff/format/whitespace; identity, claim, admission and cleanup changes also
get one focused peer review before LIVE. At final stabilization the broad
suite, delivery gate, MkDocs, namespace inventory and exact-SHA CI run once on
frozen code.

## Review delta, version 2

One focused adversarial review of checkpoint `d13a4ff` reported five
high-severity findings. Each was verified against the code before acting.

1. **Purpose at the product boundary.** The product acceptance coordinator
   applies its own repository rule, which requires the executed HEAD to be
   published, so an unpublished experimental checkpoint is refused there
   before contact; and an experimental run on a published HEAD produced an
   envelope indistinguishable from a delivery. The scalable grant now carries
   an optional `execution_purpose` (absent means delivery; any other value is
   malformed). Only the experimental seal writes it, the envelope then
   carries `experimental_measurement_is_not_a_delivery`, and the campaign CLI
   refuses an envelope whose purpose differs from its campaign. The product's
   publication rule is unchanged for every grant. Relaxing it for
   experimental grants was refused by the local permission policy as
   security-weakening; that is an operator decision, and until it is made an
   experimental acceptance needs a published checkpoint.
2. **Ledger write before index refresh.** A hard stop between them left a
   valid record the index did not name, and every later phase, cleanup
   included, refused the archive. `adopt_ledger_residue` indexes such records
   only when every indexed byte is unchanged and every unindexed file is a
   ledger record; any other drift stays a refusal. Every experimental phase
   and ledger mode adopts before it verifies.
3. **Admission not bound to the checkpoint.** A phase from another clean
   commit could be admitted under an episode opened for a different one.
   Admission now requires the phase's fresh HEAD and tree to equal the
   opening's and records them.
4. **Forced exit and user state.** The disposable-workspace recheck was only
   attested by the capture. A forced exit now also requires the main window
   title at termination to equal the non-empty title captured at launch;
   opening or saving any document changes it. A dirty workspace may still be
   retired this way because it is campaign-owned and disposable, and its
   disposition stays `_dirty_forced`, never clean.
5. **Hard stop during E4.** As in C31, owned cleanup needs the durable E4
   result; a stop between a device creation and that result leaves effects no
   governed cleanup can prove. This is kept as a limitation with the stop
   rule: stop, name the obstruction, preserve the journal, and retire the
   disposable process only under (4).

## Re-review delta, version 3

A focused re-review of `3ef6d49` found three further gaps, each verified.

1. **Measured is not accepted.** The product still reported an experimental
   success as `accepted` with exit 0 and `http_accepted: true`. The result
   now separates `measured` (a kept verdict published in time, any purpose)
   from `accepted` (delivery only). An experimental success exits 3 and its
   summary says `experimental_measured`, `execution_purpose` and publication
   `measured`, with `http_accepted: false`. The campaign CLI completes a
   phase only on the success code its own purpose implies.
2. **Residue must be a record.** Adoption now requires every unindexed file
   to be a `.json` directly under the ledger whose name is a ledger name and
   whose content is the complete record that name implies, hanging from an
   existing opening (and, for a result, its admission). A temporary file of an
   interrupted write, an unknown file or an orphan result stays a refusal.
3. **Blank launch.** A forced exit now also requires the launch record to
   prove a new unnamed document: a command line that is only the executable,
   and a non-empty title that names no file. The untitled document's unsaved
   content is the campaign's own; what anyone else typed into it cannot be
   observed without contacting Packet Tracer, which the exclusive disposable
   lab rule covers instead.

## Addendum 01: unpublished experimental checkpoint, version 4

The operator approved option 1 in `SERVER-PT-IOS-FASTLOOP-01 — Addendum 01`
(relayed to the lead; its text is kept verbatim with the campaign evidence).
Only two conditions are waived for an authorized experimental episode: that
the executed checkpoint be remotely published, and that its full CI finish
before contact. Source identity, freshness, ownership, readiness, outcome
uncertainty, evidence publication, finalization and integrity checks, the
result-publication receipt and its deadline, all remain.

The waiver is carried by validated campaign authority through the existing
internal path, never by a flag. `ExperimentalSourceAuthority` is an internal
field of `AcceptanceBoundaries`; only the campaign CLI's composition sets it,
after the charter digest, the open episode, the ledger admission of that
episode's exact HEAD and tree, the experimental preflight and the sealed
experimental grant have all been validated. The product then drops only the
`repository_upstream` refusal, and only when the authority names exactly the
grant's attempt, authorization, SHA and tree. An authority that is present
but does not match, or accompanies a delivery grant, refuses before contact.
The public product CLI never sets it, so an experimental grant presented
there, or a missing upstream, still needs publication. The envelope records
`publication_required`, the observed upstream and the authority it used.

The first review's premise that title equality proved a blank document is
superseded: a title is auxiliary. Retirement of an experimental attempt is
the CLI's `--retire`, which observes rather than trusts captures. The launch
record stores the command line and window title the CLI read from the
operating system; `--retire` refuses before any effect unless a fresh
reading still matches PID, image, creation time, command line and title and
a workspace-ownership basis is established from indexed records (restored
owned cleanup; an empty disposable baseline observed before campaign
effects; or, before setup, the blank launch with any preliminary phase
archived). It requests `CloseMainWindow`, waits a bounded time, and only
then, after a second matching reading, terminates that exact PID and records
`_forced` with its basis. Changed, unreadable or conflicting evidence
prevents the force and is recorded as a retirement attempt. `--record-exit`
never admits a forced capture. Retirement never proves restoration, and an
interrupted setup without device-level evidence stays unresolved.

## LIVE episode 1, version 5

Episode 1 ran checkpoint `1d086aa` (tree `1e709da5`), four commits ahead of
its upstream `3552d6d`, unpublished and without CI, under the work order
(`3ed40bd1`) and Addendum 01 (`594c8b28`). One campaign-launched disposable
Packet Tracer 9.0.1.0858 (PID 3248) ran attempt `b118c848`:

| Phase | Result | Operations |
| --- | --- | --- |
| Prequalification | `ready_for_catalog_review` | 25 |
| Setup | `ready` (35 devices, 36 links, VLAN/trunk foundations) | 260 |
| Acceptance | `measured`, exit 3: 30 selected, 30 accepted, 30 released | 264 |
| Cleanup | `restored` (35 removed, two observations equal the empty baseline) | 73 |

Every client fetched `http://198.18.160.2/` and observed the fresh attempt
marker; the envelope's publication link returned at 78.4 s of a 2,792 s
deadline, and it records `publication_required: false` with the validated
authority. The readiness rows confirm the diagnosis: SW-02 took six samples
of exactly seven calls each, `LRN` for five and `FWD` at 18.5 s (43 calls of
its 181); SW-01 was `FWD` on its first seven-call sample; trunk continuity
joined in one round of four single-page reads. The episode charged 622
operations and 549.5 s of the campaign allowance.

Retirement is not recorded in the archive. `--retire` refused before any
effect with `process_document_title_changed`: the process shows two visible
windows, `Cisco Packet Tracer` and `Logs - MCP BUILDER`, and .NET's main
window title switched between them after launch. The lead then made one
graceful `CloseMainWindow` request, answered no prompt, issued no
termination, and observed the exit with no Packet Tracer process and an
empty mailbox. Recording that lead-authored capture, and replacing the title
guard with a visible-window-set rule for later episodes, were both denied by
the platform permission policy; they await the operator. Until then the
exit of PID 3248 is observed but not archived, and `--retire` as delivered
cannot be relied on for this build.

## Addendum 02: retirement and evidence closeout, version 6

The operator's `SERVER-PT-IOS-FASTLOOP-01 — Addendum 02: retirement and
evidence closeout` (SHA-256
`684636f6436934029709d83e7bd651194aa6d3a7cd9e56da55d592b8660ea288`) approves
both decisions left open above: ingest the lead's retained graceful close of
PID 3248 with honest provenance, and replace the main-window-title guard with
bounded, process-bound window observation. Risk stays **L** (retirement,
evidence and process termination). The measured source stays `1d086aa` with
its tree, identities, timestamps and experimental purpose; the work starts at
`5be8920`, which changed only this brief. The lead's session narrows the
addendum further: no Packet Tracer launch (so no lifecycle smoke) and no push
(so the exact-SHA CI of the new commits stays pending).

**What the retained originals show.** The lead's session transcript keeps
every command and raw answer of the exit, byte for byte:

| UTC (clock) | Command | Raw answer |
| --- | --- | --- |
| 03:48:49 (transcript) | `--retire` at `1d086aa` | `{"outcome": "refused", "reasons": ["process_document_title_changed"]}`, then census `2` |
| 03:49:03 (transcript) | Windows of PID 3248 | main title `Cisco Packet Tracer`; visible `Cisco Packet Tracer`, `Logs - MCP BUILDER` |
| 03:49:53.0758 (OS) | Identity check, `CloseMainWindow` | `requested=True`, main title at request `Cisco Packet Tracer`; `exited=False` after 40 polls of 0.5 s |
| 03:50:21 to 03:50:25 (transcript) | `Get-Process -Id 3248` | `process 3248 exited` |
| 03:50:40.2114 (OS) | Census and mailbox, writes `close-capture.json` | `packet_tracer_processes=0`, `mailbox_pending=0` |

No termination command appears between the request and the census. In
`close-capture.json`, `observed_at_utc`, `process_count` and
`actual_exit_observed` are that command's own observations; `pid`,
`process_path`, `process_incarnation`, `method`, `requested` and
`requested_at_utc` are literals transcribed from the request's answer; and
`completion_method` and `note` are the lead's assertions. The prepared
`close_pt.ps1` was not used. A read-only query of the Application log made
for this import finds no Packet Tracer event between 03:40 and 04:00 UTC. The
ledger closing's phrase "exited after a graceful CloseMainWindow request
only" states a sequence, not a proved cause; the ledger is immutable and is
not edited.

### Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| G1 | The historical exit is imported only under this addendum | `--import-exit` refuses another campaign, attempt, episode source or addendum digest, a delivery campaign and any CI claim, before it reads the process table |
| G2 | The recorder names its own source | The import runs from a clean committed descendant, verifies that the episode commit is its ancestor and has the launch's tree, and records both sources separately; configuration, cleanup and `--retire` still require the launch's exact source |
| G3 | Originals keep their bytes and meaning | Every artifact is stored write-once with its original bytes, hash, size and path; the capture passes the existing exit rules against the launch; request time, census time and prelaunch census bind to the launch; each transcript line equals the named line of its source file; time bounds are strictly ordered, and the archive time is later and separate |
| G4 | The claim is no larger than the evidence | The record says absence observed after a graceful request, exit method unproven, no lead termination in the retained commands, and `--retire` refused with no effect; a field the lead asserted never supports the exit; no `process-exit` record is written and nothing is credited to `--retire` |
| G5 | The import is additive | A fresh census and mailbox inspection run without contacting Packet Tracer; the owned PID present or an unreadable census refuses before any write; the prior index is kept byte for byte and the new index names its digest; prior records, current status and the ledger are unchanged |
| G6 | Windows are observed, bounded and attributed | One census enumerates top-level windows with a finite deadline and returns, for the exact PID only, handle, owner PID, class, title, visibility, enablement, owner window and an identity digest, with completeness or error; other applications' titles are never read |
| G7 | Selection does not depend on focus or order | Two owned windows in either order, with or without the extension log window, select the same document window; a foreign process with identical titles is never selected |
| G8 | Doubt withholds effects | An incomplete or unattributed census, several or no document windows, a disabled document, a visible owned (modal) window, or a document title naming a file sends neither close nor kill |
| G9 | One revalidated normal close | The close names one PID and one handle; the helper rechecks owner, top-level visibility and identity digest in the same call before it posts `WM_CLOSE`; the log window is never targeted and nothing is broadcast |
| G10 | Force keeps its charter | A force needs the bounded failed close, the exact identity rechecked, the same document window unchanged, a complete census without modal windows and the durable ownership basis; a prompt is never answered, and a vanished document window with a live process is recorded, not forced |
| G11 | Already absent is not retired | An absent process gets neither close nor kill and is recorded as a retirement attempt |

### Design

**Historical import.** A new CLI mode, `--import-exit`, takes the charter, the
addendum and a lead-written manifest of at most 16 KiB. A pinned
`HistoricalExitImportAuthority` names the addendum digest, campaign, attempt,
episode and the episode's source SHA and tree; nothing else is importable.
After the charter, addendum, source and ancestry checks, the store loads the
launch, the restored cleanup and the verified index, and refuses if a
`process-exit` or an earlier import exists. The pure rule
`historical_exit_import_findings` validates the capture (through
`exit_evidence_findings` with `allow_forced=False`), the close-request output,
the prelaunch census, the field provenance, the transcript citations and the
time bounds. The CLI then takes one bounded census and mailbox inspection.
Only then does it write, in order: `authority/addendum-02.md`, each artifact
as `exit-import-<role>.<ext>`, the `exit-import` record, and a new index whose
`predecessor` names a write-once copy of the previous index under
`index-history/`. The disposition is `absence_observed_after_graceful_request`
with `exit_method: unproven`.

**Window census and retirement.** `PowerShellOwnedProcessControl.windows(pid)`
compiles one small user32 helper and enumerates top-level windows under the
existing finite helper timeout. Title and class are read only for windows the
exact PID owns, and each window's identity digest is SHA-256 of
`class + "\n" + title`, computed by the helper itself. More than 256 owned
windows, a failed enumeration or malformed output make the census incomplete.
`close_window(pid, handle, digest)` passes two validated integers and a hex
digest, rechecks in the same call and posts `WM_CLOSE` only if everything
still matches. `select_document_window` accepts exactly one visible, enabled,
unowned window that is not the extension log window (`Logs - MCP BUILDER`,
observed on 9.0.1.0858) and names no file; a visible owned window is a modal
or ambiguous finding. `--retire` observes the identity (PID, image, creation
time and command line; no longer the main title), takes a census, selects,
re-observes the identity and closes that one window. After the bounded wait
it takes a second census; a force needs the same window with the same digest
and no modal. `--record-launch` also stores the launch census as auxiliary
evidence. The graceful method becomes `WM_CLOSE` to the selected handle,
recorded with its target; `exit_evidence_findings` still accepts historical
`CloseMainWindow` records.

### Invariants

The ownership basis (launch, baseline, operations, restored cleanup,
exclusive lab) is the only destructive authority; handles and titles are
auxiliary. No window, title or name set proves that a user document is
absent. Ordinary source binding for C31 and for every effecting FASTLOOP mode
is unchanged. No counter resets. Historical records, including the refusal
and the HTTP, cleanup and publication records, are never rewritten.

### Test design

Unit: selection and force rules for two windows in either order, the log
window present or absent, a foreign PID with identical titles, a modal
window, a disabled or file-naming document, ambiguity and an incomplete
census; the helper's commands contain only validated integers and a digest,
and its output parser fails closed; import findings for each tampered field,
ordering and provenance. Integration through the CLI and store: `--retire`
with a fake process control for focus flips, PID reuse, handle reuse at close
time, an incomplete census, a changed or ambiguous document, a modal prompt,
a close that does not exit, a document that vanishes while the process
stays, and an already-absent process, each asserting which effects were
sent; and `--import-exit` on a temporary archive, asserting byte-exact
artifacts, the predecessor index, unchanged prior files, no `process-exit`,
and that every refusal writes nothing. The real helper runs against an
off-screen window the test creates, opt-in and Windows-only. System and
acceptance: the import runs once on the real archive; no LIVE retirement is
repeated and no smoke is run. Final stabilization runs the full suite, the
delivery gate, MkDocs, the namespace inventory and whitespace checks once on
frozen code.
