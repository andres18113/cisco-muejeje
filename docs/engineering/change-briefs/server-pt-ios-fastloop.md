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
