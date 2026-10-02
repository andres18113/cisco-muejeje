# SP2 prospective helper closure review package

Status: READY_FOR_INDEPENDENT_HELPER_REVIEW. Risk L; existing brief design.
Integration writer: `/root/sp2_helper_closure`. No LIVE/allocation performed.

Source checkout is `Cisco-MCP-server-services-goal-foundations`, branch
`feature/server-pt-goal-foundations`, commit
`ece5fca0cf9b997aed185b86367cd00fa6e9cd6c`, tree
`2c760bd2b9e1727e149efc56eece0833c15f879f`. Only ignored governed data changed.
Helper SHA-256 identities are independent of that Git source identity.

Review `review-package/helpers.diff` for the complete ten-original to
eleven-candidate helper diff. Original and candidate byte snapshots, old/new
hashes, the caller-pin candidate and every bounded verification artifact are
in the same review package. `MANIFEST.sha256` binds its exact file set/bytes.
No executing helper can generate or accept its own replacement caller pin.

Requirements and causal dispositions are in `brief-dispositions.md`; that
section must be added to the existing maintained brief with subsequent native
archive/public integration publication. The brief already owns this design,
so it was not dirtied merely to repeat it before native execution.

## Verification

Commands run from this checkout with its local interpreter:

```powershell
$env:SP2_HELPER_SOURCE=(Resolve-Path -LiteralPath 'data/services/sp2-governed/continuation-tools').Path
.\.venv\Scripts\python.exe -B -m pytest -q data/services/sp2-governed/helper-closure-20260930T2100Z/test_helper_controls.py --junitxml data/services/sp2-governed/helper-closure-20260930T2100Z/controls-delivery.xml
.\.venv\Scripts\python.exe -m ruff check data/services/sp2-governed/continuation-tools data/services/sp2-governed/helper-closure-20260930T2100Z/test_helper_controls.py
.\.venv\Scripts\python.exe -m ruff format --check data/services/sp2-governed/continuation-tools data/services/sp2-governed/helper-closure-20260930T2100Z/test_helper_controls.py
```

- Original causal RED: 7 failed, 1 passed, 4.11s; no errors/skips.
- Fixed v1: 7 passed, 1 failed, 24.57s. Its positive failed because fixture
  capture_text normalized CRLF. The test now uses the maintained producer's
  exact byte decoding; the production predicate was preserved.
- Fixed v2: 8 passed, 3.87s.
- Expanded v3: 102 passed, 31.30s.
- Entry/maker v4: 114 passed, 28.79s.
- Final semantic/retention check: 114 passed, 36.15s.
- Delivery bytes after import sorting/CRLF: 114 passed, 39.28s, zero
  failures/errors/skips; frozen eleven helper hashes match at termination.
- Final Ruff and format exit zero; twelve Python files parse and use CRLF.

All intermediate logs/XML/exit files are retained. Earlier `ruff-final` has one
import-order failure; the final `ruff-delivery` passes after sorting that import.
No broad source suite was rerun because maintained source is byte unchanged.
The root's exact ECE full-suite and six-job CI baseline remains a source result.
These controls establish prospective helper behavior only, not native success.

## Quality self-review

The gates belong to one local authority helper, not a parallel service engine.
Every effectful helper validates the external pin before its effect. Launch
checks indexed opening authority before claim/Start-Process. Seal validates
every promised file/identity before stage creation, preserves failed and dirty
cleanup metadata, rejects linked source inventory, and re-enumerates and hashes
after moving. Reusable publication verification checks every file and exact
set. No retry, grant, API, capacity, support or public capability predicate was
weakened. The real maker's mixed/capacity fixtures are composed offline.

The source-verification runner is retained as byte evidence `.py.txt` with an
archive path map; all twenty artifact bytes and the summary survive. Every
helper, including authority/maker/seal, survives in the snapshot. The old e8
tools copy remains unqualified. E7 archives and consumed accounting are exact.

After independent approval, install the candidate eleven helpers into the
exclusive prospective `lead/tools`, retain `helper-snapshot-candidate.json` as
`lead/helper-snapshot.json`, and supply its **approved** hash in
`PT_MCP_HELPER_SNAPSHOT_SHA256`. Use checkout-local Python `-B` for every helper.
Retain summary/all twenty verification artifacts under that lead. Repeat
source/CI/import/ledger/process/mailbox preflight before preparation/effects.
The candidate manifest is a review artifact, not self-approval.

Mixed11, capacity54, measured cohort public support and real registered four
input/default-catalog native acceptance remain pending. No e8 identity, plan,
opening, launch, native qualification or seal was created by this task.
