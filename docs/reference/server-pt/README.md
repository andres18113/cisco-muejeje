# Server-PT historical records

Navigation only. This directory preserves the planning, decision, assignment,
review and superseded-brief inputs of the Server-PT services workstream. They
are historical records, not an executable instruction chain, and several contain
superseded observations or readiness statements. Current authority is
`AGENTS.md`, `docs/engineering/standards.md`, the owning code and its tests, and
the current
[Server-PT services brief](../../engineering/change-briefs/server-pt-services.md).
A historical LIVE permission confers none on a new run.

`source-manifest.json` records every archived file with its origin, byte count
and SHA-256. Archived bytes are never normalized: `.gitattributes` marks these
paths `-text -diff` so each checkout reproduces the recorded digest. Statuses
are not restated here; read them in the current brief.

## Where to look

| Question | Read |
| --- | --- |
| What is accepted, in scope, or open right now | the [current brief](../../engineering/change-briefs/server-pt-services.md) |
| What a stable service contract says | [E6 architecture](../../architecture/enterprise-services.md) and the owning module |
| How a Q stage is authorized and recorded | [`docs/qa/server-services-qualification.md`](../../qa/server-services-qualification.md) |
| Why a superseded requirement said what it did | the archived records below, at their recorded source commit |

## Contents

| Path | Origin | Superseded by |
| --- | --- | --- |
| `planning/rev2.2/` | the three revision 2.2 planning inputs, Downloads, 2026-09-17 | the current brief's scope, requirement destinations and open decisions |
| `decisions/` | the TD-12 approval and the accepted S0 decision, Downloads, 2026-09-17 | still binding where the current brief says so (TD-12.1, TD-12.2) |
| `assignments/S1_Implementer_Prompt.md` | the historical S1 assignment, Downloads, 2026-09-17 | the accepted S1 baseline in the current brief |
| `reviews/S1_0bddc9a_Review.md` | the independent review of S1 `0bddc9a`, Downloads, 2026-09-17 | closed; see the accepted S1 baseline |
| `server-pt-services-brief-9973f66.md` | `docs/engineering/change-briefs/server-pt-services.md` at commit `9973f66` | the current brief, which projects it; sections 8–12 hold the S0, S1 and S4a narratives |
| `server-pt-services-brief-0850de3.md` | the same brief at the accepted S4a commit `0850de3` | the current brief; it holds the S4A-C1..C4 correction delta and its verification evidence |
| `evidence/q-batch-0850de3/` | the operator batch `server-pt-q-batch-0850de3.zip` and its 15 extracted files, 2026-09-19 | nothing: LIVE evidence is immutable. The current brief states which conclusions each record permits |
| `assignments/Codex_Continuation_A1_Q3_Q1_S1b.md` | amendment 01 to campaign `SERVER-PT-D02-Q3-Q1-AUTOFIX-01`, Downloads, 2026-09-19 | nothing yet: it is the active authority for Block F of the current brief |
| `assignments/Codex_243_Focused_Closure_and_Remaining_LIVE.md` | focused closure review addendum, Downloads, 2026-09-19 | nothing yet: it completes the active amendment boundaries and delegates the two remaining attempts conditionally |
| `evidence/campaign-d02-q3-q1-autofix-01/` | appended amendment and focused-closure ledger entries with their digests, 2026-09-19 | nothing: they extend the campaign chain without replacing any earlier entry |

The companion overlay ZIP named by the S1 review was not present, so the
individually supplied source files were used and hash-verified without
modifying or removing them.

## Q-batch evidence at `0850de3`

The three LIVE qualification records executed at
`0850de3dd94c8ada25c5b493e5638e6b0ce0351d` (tree `acc6caf`), build
9.0.1.0858. The ZIP is the accepted input (21,509 bytes, SHA-256
`e93b130a997c7f9a6363446373d744ef4feba54731dcc5571db4da969b8adfdc`); its
`MANIFEST.sha256` covers the other 14 files, and `source-manifest.json` covers
all 16, the ZIP included. Every record stays attributed to its own SHA, build
and channel.

| Run | Channel | Record | Record SHA-256 |
| --- | --- | --- | --- |
| Q0 `2026-09-18T23-39-18Z-b68e4a7b` | file | `q0-file/q0-2026-09-18T23-39-18Z-b68e4a7b.json` | `1a6ee0811c2df36e841a1eec73f8885b20ec892c6f23f3f94cb90f59c517c955` |
| Q1 `2026-09-19T00-13-08Z-985c1368` | file | `q1-file/q1-2026-09-19T00-13-08Z-985c1368.json` | `a0e2f93820d980e98551b0106615d86a89f8fb08e422b82ca01c09692fc5b005` |
| Q0 `2026-09-19T00-20-05Z-edbbc347` | http | `q0-http/q0-2026-09-19T00-20-05Z-edbbc347.json` | `5d0b919f04a83e516fcbefa0a41c59b77539e73334738b3780a05723cb4b40aa` |

`BATCH-STATUS.md` is the operator's handoff for the batch, preserved as
received. Its eligibility section was an input to a later decision, not an
authorization.

## Campaign `SERVER-PT-D02-Q3-Q1-AUTOFIX-01`

The campaign package itself stays with the operator, outside this repository:
`SERVER-PT-D02-Q3-Q1-AUTOFIX-01.zip`, 127,800 bytes, SHA-256
`1b71018ac383db84fa3ba64e58fa5a020e180e0d0b0d37cd2120e5d4e75dfa2f`, whose 80
files total 318,993 bytes. It carries the three LIVE attempt directories and
the first three correction-ledger entries.
[`evidence/campaign-d02-q3-q1-autofix-01/`](evidence/campaign-d02-q3-q1-autofix-01/README.md)
appends amendment entry 4 and focused-closure entry 5 to that chain and replaces
nothing in it.

## Adding a record

Save the closure delta, not another copy of the whole history. A new entry
needs its source (commit and path, or external origin and date), its archive
path, byte count and SHA-256 in `source-manifest.json`, a `-text -diff`
attribute for its directory, and one row above naming what supersedes it.
