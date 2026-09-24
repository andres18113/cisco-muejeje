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

## Review delta, version 7

One focused read-only adversarial review (Codex) of `4ec5d33` against
`5be8920` returned needs-attention with four findings. Each was confirmed
against the code and first reproduced as a failing regression (13 tests
RED at `4ec5d33`), then fixed inside the approved contract.

1. **Stale census at the effect (high).** The close helper rechecked only
   its target window, so a second window or a modal that appeared after the
   census did not stop the close, and the force was a PID-only
   `Stop-Process`. The census now also returns the process's creation time
   in UTC ticks and a digest of its visible window set (handle, owner
   window, enablement and identity digest, sorted, so focus and order do not
   change it). The close and a new bound termination recheck both in the
   same helper call; the termination kills through the very process object
   whose creation time it checked. `--retire` also requires the census's
   ticks to equal the launch's creation time, parsed exactly to seven
   fractional digits. The PID-only termination and `CloseMainWindow`
   helpers are removed. A force record names its bound ticks and window set,
   and one whose kill was not confirmed is recorded as an attempt.
2. **Request not bound to the process (high).** `close-request.txt` names
   neither PID nor method; the capture supplied them. The import now requires
   the retained request command to name the owned PID, its creation time,
   its image and `CloseMainWindow`, and its answer to report `requested=True`
   at the capture's request time. A repeated or contradicting field in the
   request output is refused.
3. **Interrupted import (high).** A stop between writes left unindexed files
   that blocked every later phase and could not be retried. Every import
   write now accepts its own identical bytes, and only this import's own
   files (with the snapshot of exactly the current index) are tolerated as
   residue. A retry finishes the writes; a record written before the stop is
   indexed exactly as written, after its artifacts, addendum and preserved
   index are shown unchanged, with only its derived digest restored if
   missing. Any other unindexed file still refuses.
4. **Unsupported transcript bounds (medium).** A bound only had to cite a
   line. Each transcript bound must now equal its cited answer's own
   timestamp; presence is the request command's answer reporting
   `exited=False`, and absence is the answer of a command that checked the
   owned PID and reported `process <pid> exited`.

The real originals of episode 1 pass the stricter rules unchanged.

## Re-review delta, version 8

A focused re-review of `59c69d5` confirmed that the four fixes close their
scenarios and found three further high-severity gaps. B and C were first
reproduced as failing regressions. A was a race inside the native call that
no offline double can interleave, so its regression is the opt-in native
test.

1. **Termination handle.** In Windows PowerShell's .NET Framework,
   `Process.StartTime` and `Process.Kill()` each open their own handle by
   PID, so a PID reused between them could be killed. The helper now opens
   one native handle (`OpenProcess`), reads the creation time through it
   (`GetProcessTimes`), checks the window set while it is held, and
   terminates that same handle (`TerminateProcess`). The close holds a
   handle too: while one is open, the PID cannot name another process.
   The census reads creation time the same way.
2. **Completion of an unvalidated record.** A retry used to index an
   unindexed record after checking only its self-consistency, so a planted
   or altered record could become immutable. A retry now reads the manifest
   and originals again, reruns every import rule and the transcript check,
   and rebuilds the record. Only three values are taken from the earlier
   run, each checked: its recorder (a clean descendant of the episode
   source), its census (owned PID absent, Packet Tracer not contacted) and
   its archive time (not in the future). The stored bytes must equal the
   rebuild exactly, and every file it names must hold the stated bytes.
3. **Identity not guarding the receiver.** Finding the identity strings
   anywhere in the command did not prove they guarded the object that
   received `CloseMainWindow`. Only the exact retained request form is now
   supported: `$p` is `Get-Process -Id $pidOwned`, the guard compares its
   creation time, image and command line with the launch's and throws before
   any request, the close goes to that `$p`, and nothing after it rebinds
   `$p` or `$pidOwned`, closes again or terminates. The absence command must
   end in the owned-PID check whose only `process <pid> exited` answer is
   its else branch. A transcript that keeps an input twice (as sent and as
   recorded) is one distinct command.

The real originals of episode 1 still pass every rule unchanged.

## Final review delta, version 9

A third focused review (of `792a233`) found three more high-severity gaps,
all reproduced first as failing regressions. The lead's own review of the
fix then found two more of the same kind, also reproduced first. This is
the last Codex review the addendum's limit of three offline subagents
allows, so this delta has self-review only.

1. **An unrelated `else` could report absence.** The absence command must
   now be exactly the retained form: a compile-only `Add-Type` here-string,
   then one `if (Get-Process -Id <pid> ...) { [W2]::Titles(<pid>) ... } else
   { "process <pid> exited" }`. The here-string is double-quoted, so it must
   contain no `$` (self-review: a `$(...)` in it would run).
2. **Conflicting copies of a command.** A transcript line keeps a tool input
   twice. The command is now the line's one `tool_use` input, and every
   `command` field on the line must be byte-identical to it.
3. **A completion trusted the interrupted run's census.** A retry now always
   takes its own census, which must find the owned PID absent. A completion
   also writes an `exit-import-completion` record: the completed record's
   digest, the new census, its own recorder source, and the statement that
   the earlier census was reported by the interrupted run and not observed
   again. The earlier census must be well formed and taken between its
   archive time and now. A completion that was itself interrupted is refused
   for an operator decision.
4. **An error could skip the request guard (self-review).** The request form
   does not stop on errors, so a guard expression that errors skips the
   `throw`. The answer's first output must now be `requested=True at=<time>`,
   with nothing before it.

The real originals of episode 1 pass every rule unchanged.

## Closeout, version 10

**Import executed.** `--import-exit` ran once, at the clean committed
recorder `6b2ee840897f52818a2e72459554f5c499eff23c` (tree `6a1255fa`), a
descendant of the episode source `1d086aa` (tree `1e709da5`, ancestry
verified). It exited 0 with `absence_observed_after_graceful_request`,
`exit_method: unproven` and `retire_credited: false`. Its archive time is
2026-09-24T13:04:00.609Z. The record `exit-import.json` has SHA-256
`2181fd9c…d783f6`. The new index (`826bbe66…`) names its predecessor
`e131c1bd…`, which is the pre-import index kept byte for byte under
`index-history/`. Of the 148 archive files present before the import, only
`index.json` changed. Nine files were added: the addendum, five artifacts,
the record and its digest, and the preserved index. The current status and
the ledger are unchanged, and no `process-exit` record exists. The fresh
census found no Packet Tracer process and no pending mailbox entry, without
contacting Packet Tracer.

**Erratum in the immutable record.** Its `exit_instant` sentence says the
exit came "after presence_last_reported_by_utc". That time is when the
request's last presence poll *answered*; the poll itself came earlier, so the
exit may precede that time. The correct bound is after the last presence
poll, whose own time was not recorded, and before the absence reading,
whose answer arrived by `absence_first_reported_by_utc`. The record is not
rewritten. Its `time_bounds` name both values as report times, and one of
its limitations says transcript times bound when an answer arrived. The
claim text in `historical_exit_claim` is corrected, with a regression, for
any later rebuild.

**Claim boundaries.**

- *Measured HTTP behavior.* 30 selected, 30 with admissible readiness before
  their request and a fresh marker fetched by IP, 30 released. The link
  returned at 78.375 s of 2,792 s. The product summary and status classify
  this as `measured` (exit 3, `http_accepted: false`). The envelope and
  publication receipt keep the profile's own `http_accepted: true` beside the
  limitation `experimental_measurement_is_not_a_delivery`. No delivery
  acceptance is claimed.
- *Cause.* The six-call readiness sample could not complete the observed
  paginated `show spanning-tree` read, which prevented readiness admission.
  After the correction the maintained product path measured fresh HTTP
  content for all 30 selected clients. The network was not always converged:
  this episode reports `LRN` before `FWD` on SW-02. Seven calls is what these
  page layouts needed, not a universal cost, and sixteen is not proven for
  arbitrary topology sizes.
- *Observed semantic restoration.* Cleanup was archived `restored`: 35
  devices removed and two observations equal to the empty baseline. Client
  release and process retirement do not prove restoration.
- *Process retirement.* PID 3248's absence is observed and archived with its
  originals. The method is unproven, the instant is bounded as above, and
  `--retire` refused and is not credited. The new window-census retirement
  is verified offline and against a synthetic off-screen window only; no
  lifecycle smoke ran, because this session was not authorized to launch
  Packet Tracer.
- *CI.* Exact-SHA CI exists only for `5be8920` (run 35954462368, six jobs
  green). The new commits were not pushed in this session, so their CI is
  pending.
- *Independent acceptance.* None. The three Codex reviews are peer reviews.

**Shared consumers that keep the old sampling contract.** Only the D-WEB
diagnostic does: `_d_web_forwarding` and `_d_web_after`
(`qualify_server_services.py`) call `observe_access_forwarding` with the
runtime default of six calls per sample and no episode allowance, mirrored
by `D_WEB_FORWARDING_SAMPLE_CALLS = 6`. Any other caller that left
`sample_calls` at its default would get the same. The readiness gate, used by
the MCP tool and both acceptance profiles, uses sixteen with the episode
allowance; trunk continuity has no default and its caller passes sixteen.
Voice's access-forwarding wait never used the forwarding sample: it reads
through the general IOS executor with `show spanning-tree` continuation
qualified, so version 1's statement that Voice kept a six-call sample was
wrong. Its multi-page behavior was not re-measured. Nothing here changes
D-WEB or Voice or replays their campaigns, and these limits do not affect
the recorded HTTP sample.

**Historical gaps, not repaired by rerunning.** The exit's instant and cause
were not observed. Earlier indexes from the episode were replaced in place;
only the index before the closure survives. The `--retire` refusal was only
printed at `1d086aa`, and its archived copy is the transcript excerpt. No
window census exists between the request and the exit, because the
request's listing failed and the next one found the PID gone. The ledger
closing's wording states a sequence as if it were a cause; it is immutable.

**Package.** One portable, hash-verified package on the operator's Desktop,
named `SERVER-PT-IOS-FASTLOOP-01-FINAL-<delivery SHA>`. It holds the full
campaign archive with the closure, the product-store sources it pins, the C31
originals behind the pagination diagnosis with their index identities, the
lead's lab files, the import inputs, source identities and a Git bundle,
verification outputs, and `FINAL-MANIFEST.sha256`.

## Addendum 03: mandatory native retirement, version 11

The operator's `SERVER-PT-IOS-FASTLOOP-01 — Addendum 03: Mandatory native
retirement qualification, in the same FASTLOOP` (SHA-256
`8bb289c581829ca6ad2aa98b8e9859e657301ccb33150eb146db51a1515f3e84`) requires
LIVE verification of the window-census retirement. It authorizes up to three
lifecycle attempts of at most 300 s each and 900 s combined, with zero bridge
operations, in a campaign-launched disposable Packet Tracer. Offline tests
alone do not complete it. The work starts at the published reference
`fcf406afee7a6dd3de67928433afea3cfc32f6bc` (tree `d472078d`), with exact-SHA
CI run 36034321658 green in all six jobs. Risk stays **L**: retirement
selection, process effects, ledger authority and evidence.

**Defect.** `select_document_window` selects the only visible, enabled,
unowned window whose title is not the log title and names no file. It never
reads `class_name`. If the document window is gone and only an unowned
`#32770` dialog titled `Save changes`, or an unknown window titled `Startup
notice`, remains beside the log, that window is selected and receives
`WM_CLOSE`. A complete census and a matching digest do not make it a
document. The defect is in design: the rule treats "not the log" as "the
document".

**What is known before the laboratory.** The document title `Cisco Packet
Tracer` and the log title `Logs - MCP BUILDER` were observed on 9.0.1.0858 in
episode 1's listing of PID 3248. The 2026-09-15 read-only UIA inventory of
this build also names the application window (`PtApp.CAppWindowBase`, Qt class
`CAppWindow`) `Cisco Packet Tracer`. The log window was unowned in episode 1,
because .NET reported it as the main window, and .NET considers only unowned
visible windows for that. The installed build ships Qt 6.8.7
(`Qt6Core.dll`/`Qt6Gui.dll` file version `6.8.7.0`). No retained record holds
the Win32 class of either window: the only class-bearing listing in episode 1
ran after the process had exited, and `Qt663QWindowIcon` in the tests is an
invented fixture value.

**Checkpoint freeze.** The source that records a laboratory's launch must
also retire it (`--retire` requires the launch's exact source), and no source
may change while that laboratory lives. The build's signature must therefore
be in the checkpoint before launch, and the laboratory's census tests it
before any effect. The expected classes are the two that Qt 6.8.7 registers
for an ordinary top-level window with a system menu: `Qt687QWindowIcon` for a
raster or Direct3D surface and `Qt687QWindowOwnDCIcon` for an OpenGL surface.
They are derived from the installed Qt version, not measured. Qt's other
window classes are not accepted in either role: tool, popup and tooltip
windows, and a dialog without a system menu (`Qt687QWindow`). If the census
contradicts the expectation, `--retire` refuses and sends nothing, the
refusal is kept, and the laboratory stays open with its ownership recorded
as unresolved. Correcting the signature then needs a new checkpoint and a new
attempt.

### Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| H1 | A document is identified positively and per build | A window is the document only if its build has a pinned signature, its class is one of that build's document classes, and its title is the build's document title. No build signature, or a launch that does not name its observed build, selects nothing (`document_signature_unestablished`) |
| H2 | Known dialogs and unknown windows withhold every effect | A visible `#32770` (`dialog_window_visible`) or any visible unowned window matching neither role (`unclassified_window_visible`) sends no close, force, click or dismissal, whether the document is present or absent. This includes a `#32770` titled `Cisco Packet Tracer` and a Qt tool window with the document title |
| H3 | Titles stay auxiliary | A matching title never selects a window whose class, owner, visibility, enablement or process does not match. A title never shows that no valuable work exists |
| H4 | Legitimate order and focus changes are preserved | Document and log in either order, with the log absent or with hidden windows, select the same document. Process creation, image, command line, attribution, completeness and ownership checks are unchanged |
| H5 | The record states how the document was identified | The retirement record and every retirement attempt carry the signature used (build, classes, titles, basis) and the census it was applied to |
| H6 | The retirement record agrees with its raw observations | The exit record keeps each absence reading's start and answer times. It bounds the exit after the last reading that found the process present and before the answer of the first reading that found it absent, unless wall and monotonic time disagree between those readings. It also keeps the mailbox's pending count before the close and after the exit, and the final Packet Tracer process count |
| H7 | A lifecycle episode admits no bridge operation | An episode may allocate zero operations. Such an episode refuses every phase admission, including cleanup's protected draw. Its time is charged from opening to closing, and at least its whole allocation; a closing earlier than its opening is refused |
| H8 | The native sequence runs on the maintained route | The lab is one fresh, unnamed 9.0.1.0858 instance launched by the lead, `--record-launch`, a read-only census through the product's reader, `--retire`, and a reload of the persisted record, all in an episode opened at a clean local checkpoint before launch |

### Design

`server_pt_process_evidence` gains a `BuildWindowSignature` per Packet Tracer
build, with a `WindowRole` for the document and for the extension log (class
set and exact title) and a `basis` sentence. `PT_WINDOW_SIGNATURES` pins only
9.0.1.0858, and `DIALOG_WINDOW_CLASSES` names the native dialog class
`#32770`. `window_signature_for_launch` returns the signature of the build
recorded on the launch (`observed_product_version` or
`observed_file_version`), or `None`. `select_document_window` and
`force_window_findings` require the signature as a keyword. They keep their
census checks in the same order: error, incarnation, attribution,
completeness. Each visible window is then classified as owned, dialog,
document, log or unclassified, and exactly one enabled document is required.
`exit_evidence_findings` requires a `WM_CLOSE` target to classify as that
build's document. `--record-launch` also stores the build versions the OS
reported (experimental campaign). `--retire` looks up the signature before
its census, records the signature on every attempt and on the exit, keeps
the timed absence readings and the mailbox state, and changes nothing about
the force contingency. Before it observes anything, `--retire` now also
requires its own process to pass the existing import-isolation preflight
(checkout interpreter and package, one namespace, no test runner). This is
the AGENTS.md LIVE gate, which `--record-launch` already applied through
`phase_preflight` but the retirement effect did not. The ledger drops the
one-operation minimum for an opening and refuses phase admission in a
zero-operation episode.

No second process manager, reader or allow-unknown switch is added. The
helper, the store, the ledger and the CLI modes are the existing ones.

### Invariants

The ownership basis remains the only destructive authority; signatures,
handles and titles are auxiliary evidence that can only withhold an effect.
The historical records, the episode 1 import and its erratum are never
rewritten. No counter resets. A live laboratory's checkpoint is not changed
until that laboratory is retired or recorded as unresolved.

### Test design

Unit: each role and dialog class in both orders, with and without the log,
the document absent beside a dialog or an unknown window, a dialog titled
like the document, a Qt tool window with the document title, a file-named
document, an unknown build, and the existing incarnation, attribution,
completeness, modal and ambiguity controls. Integration through the CLI:
`--retire` with the fake process control for a dialog or unknown window
beside the log, an unestablished build signature, and a graceful exit whose
record carries the signature, the timed absence readings and the mailbox
state. It also covers the primary cause kept first when later findings add
to it, and the real isolation preflight refusing the test process before any
observation. Ledger: a zero-operation opening is admitted and refuses every phase,
cleanup included. The first run of the RED cases at `fcf406a` must show the
dialog and unknown window selected and closed. System and acceptance: the
native sequence on the real build; its record, reload and hashes are the
acceptance evidence. After stabilization the full suite, the delivery gate,
MkDocs, the namespace inventory and whitespace checks run once on frozen
code.

## Review delta, version 12

One focused Codex adversarial review of `a235b76` against `fcf406a` returned
needs-attention with three findings. Each was first reproduced as a failing
regression at `a235b76` (seven tests RED), then fixed inside the approved
contract.

1. **A capture could claim an ineligible close target (high).**
   `_document_target_proven` checked the target's class, title and PID but not
   its owner, visibility or enablement. A lead-written `WM_CLOSE` capture sent
   through `--record-exit` could therefore name an owned modal or hidden window.
   The rule now also requires an unowned, visible, enabled target, and
   `--record-exit` refuses every `WM_CLOSE` capture: only `--retire` posts one,
   and it records its own observed exit. The `--retire` path already selected
   only unowned, visible, enabled windows.
2. **A wall-clock step could persist impossible exit bounds (medium).** Each
   reading also keeps monotonic time. If wall time and monotonic time disagree
   by more than one second between any two instants a bound uses, no bound is
   claimed (`{"unavailable": "wall_clock_discontinuous"}`). The observed exit
   itself is still recorded.
3. **A zero-operation episode could lose its time charge (medium).** A closed
   lifecycle-only episode is charged at least its whole time allocation, and a
   closing earlier than its opening is refused.

## LIVE lifecycle attempt 1, version 13

Episode 2 (ledger opening `000fdce9…`, zero operations, 300 s) ran checkpoint
`c2c963f` (tree `175c4e06`), attempt `584b1b80879750dac7b51534ebb8b114`. The
lead launched one Packet Tracer 9.0.1.0858 with no argument (PID 32920,
created 18:48:11.588Z). Its `--progress-bar-server` helper (PID 52648) started
five seconds later. `--record-launch` accepted the first capture
(`blank_document_proven: true`).

**The signature held.** The product's census showed two visible, enabled,
unowned windows, both of class `Qt687QWindowIcon`: `Cisco Packet Tracer`
(handle 1838316) and `Logs - MCP BUILDER` (handle 3477076). Every other
window was hidden: a QtWebEngine `Chrome_WidgetWin_0`, a power, a
screen-change and two IME windows. A read-only UIA reading confirmed the
roles independently of titles and classes. Handle 1838316 is
`PtApp.CAppWindowBase` (Qt class `CAppWindow`), and handle 3477076 is the
extension's `PtApp.CWebView`. The OpenGL class `Qt687QWindowOwnDCIcon` was
not observed.

**The close worked; the record was refused.** `--retire` selected handle
1838316, not the log, and posted one revalidated `WM_CLOSE` at
18:48:36.531Z. No prompt appeared. Nineteen readings found the process
present, one answered `process_reading_malformed` while it was exiting, and
the reading answered at 18:49:04.472Z found it absent. The recorded bounds
are 18:49:00.726Z to 18:49:04.472Z. The census taken 0.4 s later still
counted one Packet Tracer process: the owned helper, which was still present
at 18:49:05.184Z and gone by 18:49:21.510Z. `exit_evidence_findings`
therefore refused (`process_exit_unobserved`). The attempt was kept as
`retirement-attempt-20260924T184904Z` and no `process-exit` was written.
Episode 2 closed at 18:50:12.872Z, 122.1 s after it opened, and the ledger
charges its full 300 s.

**Cause and correction.** This is an implementation defect: `--retire` took
its census the moment the owned PID was gone, while that process's own
helper was still exiting. After the owned process has exited, `--retire` now
polls the Packet Tracer census for up to 30 s (`RETIREMENT_HELPER_WAIT_SECONDS`)
until it reads zero. It keeps each census with its times
(`process_census_readings`). Zero is still required, so a helper or any
other Packet Tracer process that remains keeps the exit unarchived, and
nothing is forced. Two regressions reproduce the attempt: first RED at
`c2c963f`, then green. Attempt 1's exit stays as observed only and is never
counted as graceful retirement evidence.

## LIVE lifecycle attempt 2 and closeout, version 14

Episode 3 (zero operations, 300 s) ran checkpoint `393c500` (tree
`4fce4b17`), attempt `97493abdbba4d4e74546a11f088325f8`, on one fresh,
unnamed Packet Tracer 9.0.1.0858 (PID 52988, created 18:54:34.951Z, with
helper PID 17304). The launch was recorded on its first capture, and the OS
reported product and file version `9.0.1.0858`. The census again showed only
two visible windows, both `Qt687QWindowIcon`: `Cisco Packet Tracer` (handle
656702, UIA `PtApp.CAppWindowBase`) and `Logs - MCP BUILDER` (handle
5704128). `--retire` selected handle 656702 and posted one `WM_CLOSE` at
18:54:53.960Z. No prompt appeared and nothing was forced. Eighteen readings
found the process present and the nineteenth found it absent, so the exit is
bounded between 18:55:18.631Z and 18:55:20.190Z. The helper was counted six
more times and was gone at 18:55:28.643Z. The mailbox had no pending entry
before the close or after the exit. The record is `exited_before_setup` with
basis `blank_launch_without_phase` and SHA-256 `de8ac486…`. It was reloaded
from the verified index, and all 18 checks passed: signature, target, log
exclusion, readings, bounds, census, mailbox, status and source. Episode 3
closed 85.8 s after it opened. Totals: two of three attempts used, 207.9 s
elapsed against 600 s charged, zero bridge operations, and the campaign
ledger at 622 operations and 1,149.5 s.

**Claims, kept separate.**

- *Experimental HTTP evidence* (episode 1, `1d086aa`): unchanged. The 30/30
  fresh-marker measurement is still a measurement of that sample, not a
  delivery.
- *Historical absence evidence* (episode 1's exit): unchanged. The import and
  its erratum are not rewritten, and nothing here shows the method or the
  instant of that exit.
- *New native retirement*: graceful and observed, on the maintained
  `--retire` route at `393c500`, for the lifecycle-only attempt of a new blank
  laboratory. It demonstrates the process exit, not topology restoration, and
  it does not cover a laboratory that had campaign effects or a save prompt.
  Attempt 1's exit (`c2c963f`) is kept only as a refused retirement attempt.
- *Limitations*: the pinned class set still admits `Qt687QWindowOwnDCIcon`,
  which neither laboratory showed; narrowing it would change code after its
  LIVE exercise and is left to review. The force contingency was not
  exercised. The signature covers only 9.0.1.0858. UIA corroboration was a
  lead observation, not a product check.

## Re-review delta, version 15

A focused Codex re-check of the changes after `a235b76` returned
needs-attention with two findings. Both were first reproduced as failing
regressions at `856a3f4`: four foreign-process cases archived the exit, and a
`NaN` allocation opened an episode. Both are fixed inside the approved
contract.

1. **A non-finite allocation bypassed the lifecycle floor (high).** JSON
   `NaN` passed every comparison, and `max(elapsed, NaN)` returned `elapsed`.
   The ledger now rejects non-finite seconds in openings, records and totals.
2. **The helper wait could not tell the owned helper from a foreign Packet
   Tracer (medium).** The count-only census is replaced by an identity census
   in the same process control: PID, parent, CIM creation time, image and
   command line for each `PacketTracer*` process. A rule names each row. It
   is `owned` when the PID and creation time (at microsecond resolution) are
   the launch's. It is `owned_helper` when its parent is the owned PID, it was
   created no earlier than the launch, it carries `--progress-bar-server`,
   and its command line and any shown image are the launched executable.
   Anything else is `foreign`. `--retire` waits out only owned helpers, stops
   at the first foreign row, and refuses with
   `foreign_packet_tracer_process`. Every census keeps its rows and their
   roles. The real command was run read-only on this host: empty, one-row and
   several-row answers parse, and an unreadable creation time fails the
   census.

This changes the retirement path that attempt 2 exercised, so the delivered
code is exercised again by lifecycle attempt 3, the last one Addendum 03
allows.

## LIVE lifecycle attempt 3 and final closeout, version 16

Episode 4 (zero operations, 300 s) ran the delivered retirement code at
`1281c92` (tree `09077400`), attempt `8782534d8d49c299db2887fcb298f614`. It
used one fresh, unnamed Packet Tracer 9.0.1.0858 (PID 48180) and its helper,
PID 38500. The census again showed only `Cisco Packet Tracer` (handle
6163786, `Qt687QWindowIcon`, UIA `PtApp.CAppWindowBase`) and the log.
`--retire` posted one `WM_CLOSE` to handle 6163786 at 19:13:36.726Z. No
prompt appeared and nothing was forced. Nineteen readings found the process
present and the next found it absent, so the exit is bounded between
19:14:02.020Z and 19:14:03.595Z. The identity census then named the one
remaining process `owned_helper` five times and read zero at 19:14:10.810Z.
The mailbox had no pending entry before the close or after the exit. The
record is `exited_before_setup` with SHA-256 `725978ad…`. It was reloaded
from the verified index, and all 19 checks passed, including that every
census row was the owned process or its helper. Episode 4 closed 85.2 s after
it opened.

**Totals.** Three of the three allowed attempts were used, with 293.1 s
elapsed. The ledger charged each attempt its full 300 s, 900 s in all, which
is the combined ceiling. There were zero bridge operations, and the campaign
ledger stands at 622 operations and 1,449.5 s. Attempt 1 (`c2c963f`) was
refused after a graceful exit and is kept as such. Attempt 2 (`393c500`)
retired gracefully with the count-only helper wait, which the re-check then
replaced. Attempt 3 exercised the delivered retirement code. Version 14's
claims about the native result hold for `1281c92`, with this attempt as their
evidence. Its limitations also stand: the unobserved `Qt687QWindowOwnDCIcon`
in the class set, the unexercised force contingency, the one build, and the
UIA reading being a lead observation.

## Final review delta, version 17

A last focused Codex check of `1281c92` returned one finding, reproduced first
at `99ae845`.

**A failed enumeration could read as an empty census (high).** In PowerShell
a `Get-CimInstance` error does not terminate the command, and the helper did
not read stderr. An access-denied enumeration could therefore print `[]` and
exit 0. The census would then report no Packet Tracer process, and `--retire`
could archive an exit while a foreign one remained. The census command now
starts with `$ErrorActionPreference = 'Stop'` and passes `-ErrorAction Stop`
to the enumeration, and any stderr output makes the census unknown
(`process_census_unobservable`). An unknown census still keeps the exit
unarchived. The regression was RED against the `99ae845` process control,
where stderr with `[]` and exit 0 parsed as an empty census. It passes now,
and a CLI control confirms that an unknown census after the exit refuses. The
real command was run read-only on this host. It returned the same empty,
one-row and several-row answers as before, and a real CIM failure (an
unknown class) now returns an error instead of an empty list.

**LIVE coverage of the delivery.** Addendum 03's three lifecycle attempts are
spent, so this error-path change was not run against Packet Tracer. The
delivered retirement code differs from the code LIVE-exercised at `1281c92`
only in this census error boundary. The command's output on success is
unchanged, and that was verified natively on this host.
