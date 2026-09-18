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

The companion overlay ZIP named by the S1 review was not present, so the
individually supplied source files were used and hash-verified without
modifying or removing them.

## Adding a record

Save the closure delta, not another copy of the whole history. A new entry
needs its source (commit and path, or external origin and date), its archive
path, byte count and SHA-256 in `source-manifest.json`, a `-text -diff`
attribute for its directory, and one row above naming what supersedes it.
