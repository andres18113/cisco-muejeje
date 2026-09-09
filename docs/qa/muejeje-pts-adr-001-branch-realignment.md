# ADR-001 — `feature/muejeje-pts` branch realignment

**Status: `ADR-001 = PROPOSED`** · Analysis only. Nothing was committed, rebased,
merged, cherry-picked, reset, moved, created, deleted or pushed. Packet Tracer
was not launched. No `.pts` was built or installed. No LIVE. No runtime
implementation was modified.

Source-of-truth order applied: `src + tests + runtime evidence` > `AGENTS.md` >
repository docs > this prompt > assumptions. `AGENTS.md` was re-read first; its
blob is `b61a9bcd813b4696cde1de4acec2adf6c22d6279`, **identical** on
`feature/muejeje-pts`, `refactor/cp-live-m0-baseline` and the working tree.

---

## 1. Frozen refs

Frozen at **2026-09-09T23:32:11Z**, worktree
`.claude/worktrees/runtime-ripv2`.

| Item | Value |
| --- | --- |
| Current branch / HEAD | `feature/muejeje-pts` = `e2d912b5fe8c67077c6b753e634967f626393d87` |
| Baseline — local `refactor/cp-live-m0-baseline` | `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` |
| Baseline — remote-tracking `cisco/refactor/cp-live-m0-baseline` | `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` |
| Baseline — **real remote** (`git ls-remote --heads cisco`) | `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` |
| Expected SHA | `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` — **MATCHES all three** |
| merge-base(feature, baseline) | `a384a79f53215436f636e8f3b989365caa16e540` |
| Ahead / behind (feature vs baseline) | **6 ahead / 75 behind** |
| Working tree | clean except one untracked file: `docs/qa/muejeje-pts-v2-preflight-inventory.md` |
| Donor `feature/runtime-protocol-v6-foundation` | `f8f10f7a218d96b46cd4df5802c958257c48eb61` (never merge) |
| `feature/runtime-ripv2` | `1d0cf4638bfb236e06d40901dc7b7c36d78ab10c` at freeze — **moving; not a baseline** |

`BASELINE_MOVED` is **not** raised: the approved baseline is still the expected
SHA in all three locations.

**Publication status — decisive for strategy choice.** `feature/muejeje-pts`
exists on **no** remote (`git ls-remote --heads` against `cisco`, `fork`,
`personal`, `origin` → 0 matches each; no `refs/remotes/**/muejeje*`). The branch
is local and unpublished, so rewriting its history costs nothing to anyone.

**Checkout locks.** `feature/muejeje-pts` is checked out only in this worktree;
`refactor/cp-live-m0-baseline` is checked out in **none** (`git worktree list`),
so it can be branched from without contention. `feature/runtime-ripv2` is held by
the concurrent worktree `.claude/worktrees/cplive-ripv2`.

**Rollback material already exists.** `git reflog show feature/muejeje-pts`
retains every one of the six commits plus a `reset` on 2026-09-07 05:37:51 -0500
that discarded an unrelated commit `a8e1746` (`test(file-bridge): synchronize the
simulated engine on events, not on sleeps`) — noted so nobody mistakes it for
part of this branch's Muejeje work.

---

## 2. Six-commit classification

Patches were inspected, not only messages.

### `45dee1d` — `docs(muejeje): establish upstream preflight and offline implementation plan`
*3 doc files, +287.* Adds `docs/architecture/muejeje-runtime-operating-model.md`,
`docs/qa/muejeje-pts-offline.md`, `docs/superpowers/plans/2026-09-06-muejeje-pts.md`.

- **Upstream equivalent?** None — baseline contains none of these paths.
- **Conflicts?** No textual conflict. **Semantic: yes, structural.** It writes
  `MUEJEJE_UPSTREAM_BASE_SHA: a384a79f…` and a branch-role table declaring
  `feature/runtime-ripv2` = *"UPSTREAM, sole living product source"*. Both are
  false against the approved baseline, and `runtime-ripv2` was observed moving
  three times during the prior audit.
- **Valid Muejeje work?** Yes — the runtime operating model's architecture,
  evidence-separation and gate discipline are the durable part.
- **Obsolete assumptions preserved?** Yes — the watermark and the role table.

**→ `REPLAY_WITH_ADAPTATION`** (rewrite watermark → `e9e26b3f…` and the role
table → `refactor/cp-live-m0-baseline` **before** replay, so the false statement
never enters the new history).

### `2134aed` — `feat(muejeje): audit build inputs and report toolchain blockers`
*8 files, +999.* The core payload: `EXTENSION/manifest/muejeje-build-manifest.json`,
`src/packet_tracer_mcp/infrastructure/pts/{__init__,build}.py`,
`tools/build_muejeje_pts.py`, `tests/test_muejeje_build.py`,
`tests/test_muejeje_build_identity.py`.

- **Upstream equivalent?** None — all six code/test paths are absent from baseline.
- **Conflicts?** None textual. **Semantic: yes.** As of this commit, `build.py`
  hard-codes `_EXPECTED_REFERENCES` = the six PTBuilder script-engine files and
  the manifest lists them as required `reference_inputs`, i.e. this commit makes
  a **PTBuilder build dependency mandatory** — a direct collision with the
  project rule (see §3).
- **Rebase-sensitivity: none.** The only 40-hex pins are content hashes, not
  commit SHAs: the PacketTracer.exe SHA-256 `843579cc…` (manifest, `build.py:289`,
  `test_muejeje_build.py:46`) and a synthetic-recipe digest
  `5a026bbe…` (`test_muejeje_build_identity.py:24`). The tests drive temporary
  Git repos and assert on blocker strings; none reads the real repo HEAD.
- **Valid Muejeje work?** Yes — this is the foundation worth keeping.

**→ `REPLAY_WITH_ADAPTATION`** (replay its payload **with** `876e584`'s
`build.py` + manifest corrections folded in, so the PTBuilder-mandatory state
never exists as a commit in the new history).

### `9d88f2f` — `docs(muejeje): plan minimal owned V5 runtime and dependency inventory`
*3 doc files, +238.* Adds `docs/superpowers/plans/2026-09-06-muejeje-owned-v0.md`;
+7 lines to the operating model, +4 to the pts plan.

- **Upstream equivalent?** None.
- **Superseded?** Its dependency inventory is superseded — not by baseline, but by
  the untracked `docs/qa/muejeje-pts-v2-preflight-inventory.md`, which classifies
  13 script-engine symbols with `[E]`/`[I]` markers and per-symbol LIVE evidence.
- **Semantic issue:** it plans an **owned V5 runtime** whose relationship to the
  V6 rules (one authoritative `mcpDispatchV6`; raw JS is legacy-compatibility
  only) is undecided. The branch's own operating model already says the owned V5
  plan *"is archived and must not be executed"*.
- **Obsolete assumptions preserved?** Yes — carries `a384a79f…`.

**→ `NEEDS_ARCHITECTURAL_DECISION`** (paired with `1344789`: does an owned V5
executor exist at all, and under what V6 boundary?).

### `1344789` — `feat(muejeje): add one-shot owned V5 executor`
*7 files, +299/−3.* Adds `EXTENSION/script-engine/muejeje_runcode.js` (53 lines),
`tests/js/muejeje_test_harness.js`, `tests/js/test_muejeje_runcode.js`,
`tests/test_muejeje_runcode.py`, and un-ignores the new engine file.

- **Present in HEAD?** **No — fully reverted by `876e584` 26 minutes later.**
- **Valid Muejeje work?** **Yes, and materially so.** It is an owned `runCode`,
  which the v2 inventory ranks as PTBuilder dependency **#2** (it breaks the
  entire HTTP channel). Verified as functionally plausible: the HTTP path
  prepends its own `function reportResult(d){…}` into the JS source
  (`live_bridge.py:83-108`, `correlated_http_send_and_wait` line 124), so the
  hoisted inner declaration shadows the unused parameter — calling
  `muejejeExecuteV5(js)` with no callback does **not** break HTTP results.
- **Semantic risks (all real, none fatal):**
  1. **Undeclared toolchain dependency.** `tests/test_muejeje_runcode.py`
     `subprocess.run(["node", …])` unconditionally, with no skip guard. Node is
     present here (`v24.19.0`) but is documented in neither `AGENTS.md` nor
     `pyproject.toml`; on a machine without it the whole suite fails.
  2. **Error opacity.** It collapses every failure to `"ENGINE_EXCEPTION"`,
     discarding `String(e)`. `main.js:139` currently returns `"PT_ERROR: " + e`.
     Losing the message weakens `APPLIED != VERIFIED`.
  3. **Second engine file.** It introduces an evaluation-order dependency
     (`scriptModules_scriptEngine.htm`: files run in the order listed) against
     `build_options.engine_script_order`, which is still `null`.
  4. **Return-shape change unverified.** PTBuilder's `runCode` return contract
     was never observed; this returns a JSON receipt. The webview ignores the
     return (`try{$se('runCode',…)}catch{}`), but that is untested on PT 9.x.
  5. `muejejeObserveExecution` is referenced but defined nowhere — a test-only
     seam shipped into the engine file.

**→ `NEEDS_ARCHITECTURAL_DECISION`** (revive under an explicit V5-compatibility
boundary with the five items above resolved, or leave it in history).

### `876e584` — `wip(muejeje-pts): preserve in-progress .pts work before switching branches`
*16 files, +280/−359.* **The mixed-purpose commit — must not survive intact.**
It bundles five unrelated concerns:

| Hunk group | Files | Verdict |
| --- | --- | --- |
| (1) Remove the mandatory six PTBuilder `reference_inputs` | `build.py` (`_EXPECTED_REFERENCES` deleted, ordered-list check removed), manifest (`reference_inputs: []`) | **KEEP** — this is what satisfies the no-PTBuilder-build-dependency rule |
| (2) Security/correctness hardening | `build.py` (duplicate reference-path rejection; strict `set(item) != {"path","sha256"}`; `noncanonical` added to the invalid-input classifier), `tests/test_muejeje_build.py` (+129, strengthened regressions) | **KEEP** |
| (3) Full revert of `1344789` | deletes `muejeje_runcode.js`, `tests/js/muejeje_test_harness.js`, `tests/js/test_muejeje_runcode.js`, `tests/test_muejeje_runcode.py` | **RE-DECIDE** under the ADR for `9d88f2f`/`1344789` |
| (4) Delete PTBuilder attribution | `EXTENSION/script-engine/README.md` (removes the table naming `userfunctions.js`, `devices.js`, `links.js`, `modules.js`, `runcode.js`, `windows.js` and the no-licence rationale), `EXTENSION/README.md`, `.gitignore` comment | **DROP** — the v2 inventory proves six PTBuilder globals are still required at runtime; `AGENTS.md` still states the reference-copy fact |
| (5) Doc/watermark rewrites | operating model, both QA docs, three plans | **ADAPT** with §2's watermark correction |

- **Upstream equivalent?** None.
- **Conflicts?** None textual.
- **Obsolete assumptions preserved?** Yes — restates `a384a79f…` and asserts
  *"upstream is an ancestor of integration"*, which is false against the baseline.

**→ `REPLAY_WITH_ADAPTATION`** (split: keep (1)+(2), re-decide (3), drop (4),
adapt (5)).

### `e2d912b` — `docs(muejeje): close verified build foundation without PTBuilder prerequisite`
*2 doc files, +22/−3.* The closure record for MUEJEJE-PTS-1.

- **Upstream equivalent?** None.
- **Durable content?** Its only substantive claim — "PTBuilder prerequisite
  removed" — is already carried by `876e584` hunk group (1). What remains is a
  closure narrative verified against the **stale** base, repeating
  `a384a79f…` and *"upstream local/remote still a384a79f…"*.
- **Superseded by?** `docs/qa/muejeje-pts-v2-preflight-inventory.md`, which
  re-derives every claim against `e9e26b3f…` with evidence markers.

**→ `DROP`.**

### Summary

| Commit | Class |
| --- | --- |
| `45dee1d` | `REPLAY_WITH_ADAPTATION` |
| `2134aed` | `REPLAY_WITH_ADAPTATION` |
| `9d88f2f` | `NEEDS_ARCHITECTURAL_DECISION` |
| `1344789` | `NEEDS_ARCHITECTURAL_DECISION` |
| `876e584` | `REPLAY_WITH_ADAPTATION` (split) |
| `e2d912b` | `DROP` |

No commit is `REPLAY_AS_IS`; no commit is `SUPERSEDED_BY_BASELINE` (the baseline
contains none of this work).

---

## 3. Collision and semantic risks

### 3.1 Merge-level risk: none

Measured, not assumed:

- Files touched by the six feature commits vs. merge-base: **15**.
- Files changed by the 75 baseline commits vs. merge-base: **174**.
- **Intersection: ∅.** `comm -12` over both sorted name lists is empty, and
  `git diff --name-only a384a79f refactor/cp-live-m0-baseline --` restricted to
  every feature-touched path returns only three *different* filenames inside the
  shared directory `docs/superpowers/plans/` (baseline adds three CP-LIVE plans;
  the feature adds three Muejeje plans).
- `.gitignore` blob is `065daee…` at **both** merge-base and baseline; only the
  feature changed it (to `180c470…`). `EXTENSION/README.md` and
  `EXTENSION/script-engine/README.md` are likewise untouched upstream.

**Therefore any replay onto `e9e26b3f…` applies without textual conflict.** The
entire decision is about *content*, not about merge mechanics.

### 3.2 Project-rule collisions (flagged, not fixed)

| Rule | Collision found |
| --- | --- |
| New `muejeje.pts` is an owned artifact | No `.pts` exists; `dist/` holds only the ignored `muejeje.build.json`. **No collision** — but `build_options` are all `null`, so ownership is undefined in the recipe. |
| No PTBuilder runtime/build dependency | **Collision, two ways.** (a) `2134aed` makes the six PTBuilder files *mandatory* build inputs; only `876e584` removes that, so the intermediate history violates the rule. (b) At HEAD the *runtime* still needs six PTBuilder globals — `htmlWindow`, `runCode`, `configureIosDevice`, `allModuleTypes`, `addDevice`, `addLink` — while `876e584` deleted the documentation that said so. The rule is an aspiration the code has not met. |
| V6 typed, declarative, whitelisted, fail-closed | `1344789`'s `muejejeExecuteV5` accepts an **arbitrary JS string** and `new Function`s it. Acceptable only if fenced as V5 legacy; it is not fenced today. |
| One authoritative `mcpDispatchV6` | Not implemented anywhere in `src/`; **no `PROTOCOL_VERSION` constant exists at all** — it lives only on the donor branch. `9d88f2f`+`1344789` propose a second execution path whose boundary against the future single dispatcher is undefined. |
| `APPLIED != VERIFIED` | `1344789` collapses all errors to `ENGINE_EXCEPTION`, discarding the underlying message that `main.js` preserves as `PT_ERROR: <e>`. |
| No implicit retry/fallback after ambiguous execution | **Pre-existing, not introduced here:** `main.js:260-262` — `lwAddDevice` silently falls back to the global `addDevice` inside `try{…}catch(e){}` when the logical-workspace call returns falsy. That is an implicit fallback after an ambiguous outcome. Out of scope for ADR-001; recorded so realignment does not bless it. |
| Raw JS is legacy compatibility only | `muejeje_runcode.js` is raw-JS execution machinery. Permitted **only** if explicitly labelled V5-compatibility and excluded from the V6 path. |
| Numeric Cisco enum tables are not source of truth | **Collision.** `shared/constants.py` `PT_DEVICE_TYPE` (33 entries) and `PT_CONNECT_TYPE` (16 entries) are hand-maintained numeric tables consumed by `lwAddDevice`/`lwAddLink`; `infrastructure/catalog/modules.py` carries `module_type: int` for 151 modules. Pre-existing, untouched by the six commits, but the realigned branch inherits it. |
| `allModuleTypes` must use Cisco runtime discovery/descriptors | **Collision, with a proven path forward.** `tool_registry.py:2654` emits the PTBuilder global directly into batch JS. `poe_delivery_runtime.py:96,100` already drives the native descriptors (`module.getType()`, `device.isModuleTypeSupported(int)`, `device.getRootModule()`, `module.isHotSwappable()`). None of the six commits addresses this. |
| `lwAddDevice`/`lwAddLink` may support V5 but are not the V6 domain contract | No V6 domain contract exists to violate yet; `ptbuilder_generator.py` still emits them as the only device/link path. Recorded as a boundary to declare, not a defect to fix now. |
| PT 9.x behaviour needs target-build evidence | **Collision.** `1344789`'s `runCode` return-shape change has **zero** PT 9.x evidence, and its tests exercise Node's `vm`, not Packet Tracer. The manifest correctly pins the builder (`9.0.1.0858`, SHA-256 `843579cc…`), but no behavioural evidence exists for any owned engine file. |

### 3.3 Governance/documentation risks carried by the branch

- **8 occurrences** of the obsolete watermark `a384a79f…` across 6 tracked docs
  (`muejeje-runtime-operating-model.md:18`, `muejeje-owned-v0-offline.md:13`,
  `muejeje-pts-offline.md:15,156,201`, `2026-09-06-muejeje-owned-v0.md:23`,
  `2026-09-06-muejeje-pts-1-close.md:26`, `2026-09-06-muejeje-pts.md:46`).
- The operating model names `feature/runtime-ripv2` as *"UPSTREAM, sole living
  product source"* — a ref that moved three times during the prior audit and is
  held by a concurrent worktree.
- `muejeje-pts-offline.md` asserts *"upstream is an ancestor of integration"*;
  `git merge-base --is-ancestor` says **NO** for both baseline and ripv2.

---

## 4. Strategy comparison

| | Textual conflict | Ancestry after | Bad content retained | Verdict |
| --- | --- | --- | --- | --- |
| **A.** Rebase/replay all 6 onto baseline | none (§3.1) | correct (`e9e26b3f…`) | **all of it** — PTBuilder-mandatory intermediate, add-then-revert pair, mixed WIP, false watermarks, deleted attribution | Rejected |
| **B.** Recreate from baseline, selectively replay | none | correct | none — each defect is dropped or adapted at replay time | **Chosen** |
| **C.** Merge baseline into the feature branch | none | keeps `a384a79f…` + a merge commit | **all of it**, and permanently | Rejected |
| **D.** Keep `a384a79f…` ancestry intentionally | n/a | wrong by construction | all of it, plus a branch 75 commits behind CP-LIVE M0–M3 + PoE | Rejected |

**A** is rejected because a clean *apply* is not a clean *history*: it would
enshrine a commit that mandates PTBuilder as a build input, an
add-then-fully-revert pair, and six documents asserting a watermark that is
demonstrably wrong.

**C** and **D** are rejected on the brief's own terms — the branch is local and
unpublished (§1), so there is no reason to preserve bad ancestry, and the
branch's own operating model requires advancing the watermark before each unit.

**B** is preferred exactly as the brief anticipates: the six commits are
obsolete (`e2d912b`), mixed-purpose (`876e584`), or should not survive intact
(`2134aed`'s PTBuilder-mandatory state). Zero textual overlap makes selective
reconstruction mechanical rather than risky.

---

## 5. Recommended strategy

> **Strategy B — recreate `feature/muejeje-pts` from
> `refactor/cp-live-m0-baseline` (`e9e26b3f…`) and selectively replay only the
> valid, adapted work.**

Rationale in one line: the replay is textually free (∅ file overlap), the branch
is unpublished so history is ours to shape, and three of the six commits carry
content that must not enter the new history intact.

---

## 6. Proposed next-step procedure — **DO NOT EXECUTE**

Written for a future authorized session. Nothing below was run.

0. **Preserve the untracked report first.** Copy
   `docs/qa/muejeje-pts-v2-preflight-inventory.md` and this file to a location
   outside the repository. (They would survive a `switch -c` because neither
   path exists in the baseline tree, but do not rely on that.)
1. **Re-freeze.** Re-read HEAD, the baseline at all three locations and
   `git status`. If the baseline is no longer `e9e26b3f…`, stop and raise
   `BASELINE_MOVED`.
2. **Create the rollback anchor.** A branch or tag
   `muejeje-pts-prealign-e2d912b` at `e2d912b5…` (this is a *new* ref; it does
   not move or delete anything).
3. **Create the new branch** from `refactor/cp-live-m0-baseline` in this
   worktree. Verify `git merge-base --is-ancestor e9e26b3f… HEAD` is true and
   `git status` shows only the two untracked reports.
4. **Replay commit 1 — foundation.** Reconstruct `2134aed`'s payload **with**
   `876e584` hunk groups (1)+(2) folded in, so the PTBuilder-mandatory state is
   never committed: manifest with `reference_inputs: []`, `build.py` without
   `_EXPECTED_REFERENCES` and with the duplicate-path / strict-key /
   `noncanonical` hardening, `__init__.py`, the CLI, and both test files at their
   `876e584` strength.
5. **Replay commit 2 — governance docs, corrected.** `45dee1d` + the adaptable
   parts of `9d88f2f`/`876e584`/`e2d912b`, with **every** `a384a79f…` replaced by
   `e9e26b3f…`, the branch-role table repointed to
   `refactor/cp-live-m0-baseline`, and the false *"upstream is an ancestor of
   integration"* claim removed.
6. **Do not replay** `876e584` hunk group (4). Instead restore the upstream
   PTBuilder attribution in `EXTENSION/script-engine/README.md`,
   `EXTENSION/README.md` and the `.gitignore` comment, adding a line stating
   which six globals are still required and that removal is tracked by the ADRs
   in the v2 inventory.
7. **Do not replay** `9d88f2f` or `1344789`. Open the architectural decision
   (owned V5 executor: yes/no, and its V6 boundary) with the five risks of §2
   attached. If approved later, revive `1344789` from
   `muejeje-pts-prealign-e2d912b` with: a node-availability skip guard or a
   declared dependency, real error text preserved, an explicit
   `engine_script_order`, and a PT 9.x behavioural check.
8. **Do not replay** `e2d912b`.
9. **Then** track the two reports as normal repository documentation.

---

## 7. Rollback

- **Primary:** `feature/muejeje-pts` at `e2d912b5…` is untouched by steps 0–3;
  the anchor `muejeje-pts-prealign-e2d912b` (step 2) is a second, explicit
  handle on the same commit.
- **Secondary:** `git reflog show feature/muejeje-pts` retains all six commits
  and the 2026-09-07 reset — reachable even if a ref were mis-set.
- **Nothing is unreachable:** the branch is unpublished, so no rollback needs to
  coordinate with a remote; no `push --force` is ever involved.
- **Abort condition at any step:** leave the new branch in place, switch back to
  `feature/muejeje-pts`, and report. No `reset --hard` on a branch holding
  untracked files.
- **Untracked-file safety:** the two reports live at paths absent from every
  candidate tree, so no checkout can overwrite them; step 0's external copy is
  the belt-and-braces guarantee.

---

## 8. Post-realignment acceptance checks

Governance:

1. `git merge-base --is-ancestor e9e26b3f7cb96… <new branch>` → true.
2. `git rev-list --left-right --count refactor/cp-live-m0-baseline...<new>` →
   `0 <N>` (zero behind).
3. `git grep -c a384a79f -- docs EXTENSION` → **0** in tracked files.
4. Operating-model branch-role table names `refactor/cp-live-m0-baseline` as the
   approved baseline, and `MUEJEJE_UPSTREAM_BASE_SHA` = `e9e26b3f…`.
5. `docs/qa/muejeje-pts-v2-preflight-inventory.md` and this ADR still present.
6. `git status --porcelain` and `git diff --check` clean.

Runtime untouched:

7. `EXTENSION/script-engine/main.js` blob still `9b088246…`;
   `EXTENSION/webview/interface.js` still `fedc2656…`; `index.html` still
   `4326a2a8…`.
8. `docs/reference/cp-scale/**` byte-identical to baseline (no runtime evidence
   modified), and the 113 baseline evidence files all present.

Product:

9. Full suite with the checkout-local interpreter and a worktree-local basetemp,
   per `AGENTS.md`:
   `./.venv/Scripts/python.exe -m pytest -q --basetemp tmp/<unique> -o cache_dir=tmp/<unique>-cache`
   — expect the CP-LIVE M0–M3 + PoE baseline count plus the Muejeje build tests;
   compare against a baseline-only run, not against the stale 3857 figure.
10. `./.venv/Scripts/python.exe tools/build_muejeje_pts.py --check --builder
    'C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe'` →
    `dist/muejeje.build.json` with `source.commit` = the **new** HEAD,
    `source.clean = true`, `reference_inputs` empty, `build_recipe_id = null`,
    and no blocker mentioning a PTBuilder reference input.
11. `sys.executable` and `packet_tracer_mcp.__file__` both resolve inside this
    worktree.

Out of scope for acceptance: no `.pts`, no PT launch, no LIVE, no push.

---

## 9. ADR status

`ADR-001 = PROPOSED`

Decision requested: adopt **Strategy B**. Two sub-decisions are deliberately
deferred to their own ADR (the owned V5 executor of `9d88f2f`/`1344789` and its
V6 boundary) and do not block Strategy B.

---

## 10. Gates

```
UPSTREAM_GOVERNANCE_BASELINED = ACHIEVED
WORKING_BRANCH_BASELINED      = BLOCKED_BY_ADR_001
ADR_001_DECISION_READY        = YES
```

- **`UPSTREAM_GOVERNANCE_BASELINED = ACHIEVED`** — refs frozen; the baseline
  confirmed at local, remote-tracking **and** real-remote and equal to the
  expected SHA; merge-base, ahead/behind and the full 174-vs-15 file delta
  measured; working tree state known.
- **`WORKING_BRANCH_BASELINED = BLOCKED_BY_ADR_001`** — the branch is 75 commits
  behind the approved baseline and still asserts a false watermark; it cannot be
  called baselined until ADR-001 is decided and executed.
- **`ADR_001_DECISION_READY = YES`** — all six patches inspected, conflict
  surface measured as empty, publication status confirmed local-only, rollback
  material verified present, and a single strategy recommended.
