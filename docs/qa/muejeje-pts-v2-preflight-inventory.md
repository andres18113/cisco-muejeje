# Muejeje `.pts` v2 — preflight, V5 compatibility inventory, packaging discovery

Read-only audit executed 2026-09-09 in worktree
`.claude/worktrees/runtime-ripv2` on branch `feature/muejeje-pts`.
No `.pts` was built or installed, no Packet Tracer process was launched, no LIVE
run or PT mutation occurred, no push was made, and no PTBuilder file was
obtained, copied or vendored.

Every claim below is marked **[E]** (evidence actually observed in this session,
with the command or file that produced it) or **[I]** (inference from that
evidence). Nothing is asserted from a prior document without re-observation.

---

## 1. Preflight status (TAREA A)

### 1.1 Heads

| Ref | SHA observed | How |
| --- | --- | --- |
| `feature/muejeje-pts` (HEAD, checked out) | `e2d912b5fe8c67077c6b753e634967f626393d87` | **[E]** `git rev-parse HEAD` |
| `refactor/cp-live-m0-baseline` (local) | `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` | **[E]** `git rev-parse` |
| `cisco/refactor/cp-live-m0-baseline` (remote-tracking) | `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` | **[E]** `git for-each-ref` |
| `refs/heads/refactor/cp-live-m0-baseline` **on the remote** | `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` | **[E]** `git ls-remote --heads cisco` |
| `feature/runtime-ripv2` (local, first observation ~21:5x UTC) | `2b0d95e1b902c426425203cea3797cfe09cfb772` | **[E]** `git for-each-ref` |
| `feature/runtime-ripv2` (local, second observation 22:03:06 UTC) | `3dde3536dc49d7e228e5931876226bb9dcd9469d` | **[E]** `git rev-parse` + reflog |
| `feature/runtime-ripv2` (local, third observation, at report time) | `31af153d3449a096f768174b303442da2839c84f` | **[E]** `git rev-parse` |
| `feature/runtime-protocol-v6-foundation` (donor, never merged) | `f8f10f7a218d96b46cd4df5802c958257c48eb61` | **[E]** `git for-each-ref` |

**The expected baseline SHA matched exactly.**
`e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` is the current head of
`refactor/cp-live-m0-baseline` both locally and on the authoritative remote.
**[E]** `git ls-remote --heads cisco`, plus a `git fetch --dry-run --prune cisco`
that produced no output (nothing to update). Upstream did **not** advance beyond
the expected SHA, so the baseline audit path for "upstream moved" does not apply.

**`feature/runtime-ripv2` is a moving ref and must not be used as a stable
baseline for this unit.** **[E]** It advanced **three times during this single
audit**: `2b0d95e1` → `3dde3536` → `31af153d`. `git reflog show
feature/runtime-ripv2 --date=iso` attributes the first two to `2026-09-09
16:45:15 -0500` and `2026-09-09 16:50:11 -0500`, from a concurrent session in the
sibling worktree `.claude/worktrees/cplive-ripv2` (**[E]** `git worktree list`);
the third was observed at report time. The two commits observed in detail are
docs-only (`docs: specify POE-3B multi-port authority`, `docs: plan POE-3B
offline implementation`), and `2b0d95e1` is an ancestor of `3dde3536` (**[E]**
`git merge-base --is-ancestor`), so the movement is fast-forward, not a rewrite.
**[I]** Any figure in this report that is stated against `feature/runtime-ripv2`
is a snapshot; only the figures against `refactor/cp-live-m0-baseline`
(`e9e26b3f…`, stable and remote-confirmed) are reproducible.

### 1.2 Merge bases and ancestry

**[E]** `git merge-base` / `git merge-base --is-ancestor`:

```
merge-base(muejeje-pts, cp-live-m0-baseline) = a384a79f53215436f636e8f3b989365caa16e540
merge-base(muejeje-pts, runtime-ripv2)       = a384a79f53215436f636e8f3b989365caa16e540
merge-base(cp-live-m0-baseline, ripv2)       = e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43
octopus(all three)                           = a384a79f53215436f636e8f3b989365caa16e540

baseline is ancestor of muejeje-pts : NO
ripv2    is ancestor of muejeje-pts : NO
baseline is ancestor of ripv2       : YES
```

`a384a79f5321…` = `fix(poe): validate exact factory identities in read-only
diagnostics`, 2026-09-06 17:02:55 -0500 **[E]** `git show -s`.

### 1.3 Working tree and repository guidance

- **[E]** `git status --porcelain=v1` returned empty at session start, after the
  read-only `--check` run, and at report time. Working tree is **clean**.
- **[E]** `AGENTS.md` exists and is byte-identical across all three refs
  (blob `b61a9bcd813b4696cde1de4acec2adf6c22d6279` on `feature/muejeje-pts`,
  `refactor/cp-live-m0-baseline` and `feature/runtime-ripv2`). No `CLAUDE.md`
  exists. It is the only tracked `AGENTS.md` in the repository.
- Relevant `AGENTS.md` content re-read this session **[E]**: run tests with the
  checkout-local `.venv`; never build JS with raw f-strings (use `json.dumps`
  per field); **never guess a PT API signature**; `EXTENSION/script-engine/` —
  *"`main.js` is ours (tracked); the rest are PTBuilder reference copies
  (gitignored)"*; webview CORS / `this-sm:` origin / IPC availability **cannot**
  be verified from tests.
- **[E]** `feature/muejeje-pts` has **no configured upstream**
  (`git config --get branch.feature/muejeje-pts.remote` → unset;
  `git rev-parse --abbrev-ref …@{upstream}` → `fatal: no upstream configured`).
- **[E]** The remote-tracking ref `fork/refactor/cp-live-m0-baseline` points at
  `8ba24fe7896114eeab15eeacff84d928c02e0a5f`, which `git ls-remote` shows is
  **not** the branch head on that URL. `fork` and `cisco` are configured to the
  same URL (`https://github.com/andres18113/cisco-muejeje.git`) **[E]**
  `git remote -v`. **[I]** `fork/*` is a stale remote-tracking alias; a baseline
  must never be read from it.

### 1.4 GOVERNANCE_BASELINED

**Reached.** Heads, merge-bases, the complete delta (§2), the source-of-truth
ordering and a clean working tree are all demonstrated above and in §2.

**Governance finding the gate does not by itself express:** the working branch is
**not built on the declared baseline**. `feature/muejeje-pts` forked at
`a384a79f` and is **75 commits behind / 6 ahead** of
`refactor/cp-live-m0-baseline`. Any statement of the form "this branch reflects
the baseline" is false today. The V5 script-engine surface happens to be
unaffected (proved in §3.1), but the CP-LIVE / PoE product surface is not.
The branch's own operating model still records
`MUEJEJE_UPSTREAM_BASE_SHA: a384a79f…`, i.e. the stale watermark **[E]**
`docs/architecture/muejeje-runtime-operating-model.md:18`.

---

## 2. Upstream delta (TAREA A, continued)

**[E]** `git rev-list --left-right --count`:

| Comparison | behind | ahead |
| --- | ---: | ---: |
| `muejeje-pts` vs `cp-live-m0-baseline` | 75 | 6 |
| `runtime-ripv2` vs `cp-live-m0-baseline` | 0 | 2 |
| `muejeje-pts` vs `runtime-ripv2` | 77 | 6 |

**[E]** `git diff --stat refactor/cp-live-m0-baseline...feature/muejeje-pts` —
what the 6 branch commits add (15 files, +1830 / −70):

```
.gitignore                                               |   5 +-
EXTENSION/README.md                                      |  50 +-
EXTENSION/manifest/muejeje-build-manifest.json           |  33 +
EXTENSION/script-engine/README.md                        |  54 +-
docs/architecture/muejeje-runtime-operating-model.md     | 111 +
docs/qa/muejeje-owned-v0-offline.md                      |  78 +
docs/qa/muejeje-pts-offline.md                           | 242 +
docs/superpowers/plans/2026-09-06-muejeje-owned-v0.md    | 243 +
docs/superpowers/plans/2026-09-06-muejeje-pts-1-close.md |  36 +
docs/superpowers/plans/2026-09-06-muejeje-pts.md         | 135 +
src/packet_tracer_mcp/infrastructure/pts/__init__.py     |   5 +
src/packet_tracer_mcp/infrastructure/pts/build.py        | 350 +
tests/test_muejeje_build.py                              | 445 +
tests/test_muejeje_build_identity.py                     |  69 +
tools/build_muejeje_pts.py                               |  44 +
```

**[E]** `git diff --stat refactor/cp-live-m0-baseline feature/muejeje-pts`
(two-dot — what the branch tree lacks relative to the baseline):
**189 files changed, 6788 insertions(+), 39184 deletions(-)**.

**[E]** Directory shape of the 75-commit delta (`git diff --name-only`, grouped):
65 paths under `tests/`, 25 under
`src/packet_tracer_mcp/application/cp_scale_live/`, 10 under
`infrastructure/execution/`, plus `docs/reference/cp-scale/**` live evidence,
`tools/poe*_live.py`, and 4 deleted `cp_scale_live*` infrastructure modules.
The 75 commits are the CP-LIVE M0–M3 refactor and the PoE/PSE evidence programme.

**[E] The delta does not touch any JavaScript-generation surface.**
`EXTENSION/script-engine/main.js`, `EXTENSION/webview/interface.js` and
`EXTENSION/webview/index.html` are byte-identical between the two refs
(blobs `9b088246…`, `fedc2656…`, `4326a2a8…` on both).

**Two documentation regressions introduced by the branch, worth naming:**

- **[E]** The branch rewrote `EXTENSION/script-engine/README.md`, deleting the
  upstream table that **names the six PTBuilder reference files**
  (`userfunctions.js`, `devices.js`, `links.js`, `modules.js`, `runcode.js`,
  `windows.js`) and their licence rationale, replacing it with prose stating
  "PTBuilder is not a mandatory runtime/build dependency".
- **[E]** The branch rewrote the `.gitignore` comment recording the same fact.
  `AGENTS.md` (unchanged, and authoritative per rule 9) still states:
  *"`main.js` is ours (tracked); the rest are PTBuilder reference copies
  (gitignored)"*.

**[I]** The removed upstream text is factually correct about the *current
sources* — §3 proves six PTBuilder-supplied globals are still required at
runtime — and the replacement text states an *intent*, not the code's state.
Rule 9 resolves the contradiction in favour of `src/` + `AGENTS.md`.

---

## 3. V5 compatibility inventory (TAREA B)

### 3.1 Method, and why this inventory is baseline-valid

Two independent extractions, each run over **both** trees:

1. **[E]** An AST scan (Python `ast` over every `.py` under `src/` and `tools/`)
   collecting identifiers called as bare globals inside JS-looking string
   constants, minus identifiers defined or bound as parameters within the same
   string, minus JS builtins. Run against the working tree and against a
   `git archive refactor/cp-live-m0-baseline src tools` extraction.
   **Result: identical 21-symbol sets; zero difference in either direction.**
2. **[E]** A raw-text scan for `"<ident>(` across both trees (this one catches
   f-string emissions the AST scan cannot). The only differences are Python
   identifiers (CP-LIVE / PoE classes and functions); **no script-engine global
   appears on either side of the difference.**

Reinforcing file-level check **[E]**: of the 20 Python modules that emit
script-engine JS, 17 are byte-identical between the two refs. The three that
differ (`ios_terminal.py`, `poe_delivery_runtime.py`, `typed_ping.py`) add only
Python-side helpers and `ipc` *method* calls (`getDeviceAt`, `getDeviceCount`,
PoE inline parsing); they introduce **no new bare global**.

**[I]** This inventory therefore describes `feature/muejeje-pts` **and**
`refactor/cp-live-m0-baseline` equally. The 75-commit gap does not change the V5
emission contract.

The seed list in the task was not assumed complete; it was verified and
**extended** by six symbols (`configureIosDevice`, `addDevice`, `addLink`,
`allModuleTypes`, `runCode`, `htmlWindow`), plus `reportResult` and `getDevices`.

### 3.2 What `main.js` defines, and what it leaves undefined

**[E]** `EXTENSION/script-engine/main.js` (367 lines, tracked, ours) defines:
`builder` (+`init`/`cleanUp`/`menuClicked`), `startBridge`, `mcpTokenCandidates`,
`getMcpToken`, `getMcpTokenInfo`, `fileBridgeStatus`, `mcpBridgeDir`,
`runFileBridgeCommand`, `fileBridgeTick`, `startFileBridge`, `GLOBAL`,
`installMcpHelpers`, `main`, `cleanUp`.

**[E]** `installMcpHelpers()` installs six globals onto `GLOBAL`:
`addModule`, `lwAddDevice`, `lwAddLink`, `configurePcIp`, `configurePcIpv6`,
`swapLaptopToWireless`. Its own comment states the intent precisely:
*"lwAddDevice / lwAddLink no existen en userfunctions.js … Las demas
sobreescriben a las nativas"* (`main.js:216-218`).

**[E]** `main.js` itself calls identifiers it does not define, and which are
defined in **no tracked file** (`grep -rn` over all of `EXTENSION/`):
`htmlWindow` (line 355), `allModuleTypes` (lines 236, 343), `addDevice`
(line 261) — plus Cisco natives `ipc` and `_ScriptModule` (line 16).

### 3.3 Symbol inventory

Status legend: `OWNED` = defined by our tracked source; `OWNED*` = defined by us
but internally dependent on a PTBuilder-supplied symbol; `PTBUILDER_DEPENDENT` =
required at runtime, defined by no tracked file; `CISCO_NATIVE` = provided by the
Packet Tracer Script Engine.

#### `lwAddDevice(name, deviceType, model, x, y)` — **OWNED\***
- **Emitted by [E]**: `infrastructure/generator/ptbuilder_generator.py:31`
  (`generate_device_command`); `infrastructure/execution/probe_runtime.py:288,289,1066,1067`;
  `infrastructure/execution/poe_delivery_runtime.py:187,188`.
- **Operations [E]**: full topology deploy (`generate_ptbuilder_script` →
  `deploy_executor`, `manual_executor`, `packet_tracer_physical_runtime`,
  `full_build`, `generate_script`); probe device creation; PoE fixture creation.
- **Implementation [E]**: `main.js:250-263` —
  `ipc.appWindow().getActiveWorkspace().getLogicalWorkspace().addDevice(type, model, x, y)`,
  then rename via `ipc.network().getDevice(auto).setName(name)`.
- **PTBuilder dependency [E]**: *indirect*. `main.js:261` falls back to the
  global `addDevice(name, model, x, y)` when `lw.addDevice` fails silently (the
  comment cites `Laptop-PT` returning `""`).
- **`ipc.*` used [E]**: `…getLogicalWorkspace().addDevice`,
  `ipc.network().getDevice`, `device.setName`.
- **Offline coverage [E]**: 12 test files reference it.
- **LIVE evidence [E]**: **none** — zero occurrences across all tracked
  `docs/reference/cp-scale/**` on the baseline ref.
- **Cisco-API replacement**: **[E]** the enum values are already owned —
  `shared/constants.py:60` `PT_DEVICE_TYPE` (33 entries), annotated *"de
  class_logical_workspace.html addDevice doc"*. **[I]** the primary path is
  already PTBuilder-free; only the fallback is not.

#### `lwAddLink(d1, p1, d2, p2, cable)` — **OWNED**
- **Emitted by [E]**: `ptbuilder_generator.py:41`; `probe_runtime.py:1082,1083`;
  `poe_delivery_runtime.py:269,270,271`.
- **Operations [E]**: deploy link creation; probe link; PoE fixture link.
- **Implementation [E]**: `main.js:266-277` — `lw.createLink(d1,p1,d2,p2,typeInt)`
  with a 16-entry string→enum table (8100–8114) inline.
- **PTBuilder dependency**: **none**.
- **`ipc.*` used [E]**: `…getLogicalWorkspace().createLink`.
- **Offline coverage [E]**: 8 test files.
- **LIVE evidence [E]**: none in tracked evidence.
- **Cisco-API replacement**: already native. **[E]** `PT_CONNECT_TYPE`
  (`shared/constants.py:70`) cites *"class_logical_workspace.html createLink doc"*.

#### `addModule(deviceName, slot, model)` — **OWNED\***
- **Emitted by [E]**: `ptbuilder_generator.py:111` (inside the replay-safe
  `generate_module_command` receipt); `tool_registry.py:2484,2515` (`pt_add_module`).
- **Operations [E]**: `pt_add_module`, plan module insertion, serial/physical slices.
- **Implementation [E]**: `main.js:230-244` — power-cycle, then native
  `device.addModule(slot, allModuleTypes[model], model)`, then `skipBoot()`.
- **PTBuilder dependency [E]**: *hard*, via `allModuleTypes`.
- **`ipc.*` used [E]**: `ipc.network().getDevice`, `device.getPower/setPower`,
  `device.addModule`, `device.skipBoot`.
- **Offline coverage [E]**: 3 test files (incl. `test_module_port_effect_contract.py`).
- **LIVE evidence [E]**: none under that name in tracked evidence.
- **Cisco-API replacement**: **strong candidate.** **[E]** the native call
  already takes an integer type; `infrastructure/catalog/modules.py` carries
  `ModuleSpec.module_type: int` for 151 modules; and
  `poe_delivery_runtime.py:96,100` already drives the native
  `module.getType()`, `device.isModuleTypeSupported(int)`,
  `device.getRootModule()`, `module.isHotSwappable()` surface.
  **[I]** `allModuleTypes` is a lookup table only; substituting the integer from
  Python removes the dependency — but that the catalog integers equal PT's
  expectations is **not yet proven** (unknown #4).

#### `swapLaptopToWireless(deviceName)` — **OWNED\***
- **Emitted by [E]**: `ptbuilder_generator.py:143` only.
- **Operations [E]**: wireless-laptop deploy (`plan.devices` with `wireless=True`).
- **Implementation [E]**: `main.js:338-349` — power off, `removeModule("0")`,
  `addModule("0", allModuleTypes["PT-LAPTOP-NM-1W"], "PT-LAPTOP-NM-1W")`.
- **PTBuilder dependency [E]**: *hard*, via `allModuleTypes`.
- **Offline coverage [E]**: 2 test files (`test_wireless.py`, `test_regressions_runtime.py`).
- **LIVE evidence [E]**: none.
- **Cisco-API replacement**: as for `addModule`.

#### `configurePcIp(device, dhcp, ip, mask, gw, dns, iface)` — **OWNED**
- **Emitted by [E]**: `execution/configuration_runtime.py:31,42`;
  `execution/enterprise_configuration_runtime.py:839,850`;
  `ptbuilder_generator.py:213,216,221`.
- **Operations [E]**: every host-addressing path — deploy, enterprise
  configuration, and (through `configuration_runtime`) 31 modules under
  `application/use_cases/` and `domain/enterprise/models/`.
- **Implementation [E]**: `main.js:280-310` — port discovery over
  `device.getPorts()` matching `Ethernet`/`Wireless0`, then `setDhcpFlag`,
  `port.setIpSubnetMask`, `setDefaultGateway`, `port.setDnsServerIp`.
- **PTBuilder dependency**: **none** — `main.js` overrides whatever PTBuilder
  defines, precisely to stop hardcoding `FastEthernet0`.
- **Offline coverage [E]**: 11 test files.
- **LIVE evidence [E]**: none under that name in tracked evidence.
- **Cisco-API replacement**: already native.

#### `configurePcIpv6(deviceName)` — **OWNED**
- **Emitted by [E]**: `ptbuilder_generator.py:224` only (`plan.dual_stack`).
- **Operations [E]**: dual-stack deploy, SLAAC hosts
  (`domain/services/ip_planner.py:134`).
- **Implementation [E]**: `main.js:314-331` — `port.setIpv6Enabled(true)`,
  `port.setIpv6AddressAutoConfig(true)`.
- **PTBuilder dependency**: **none**.
- **Offline coverage [E]**: 2 test files (`test_ipv6.py`, `test_regressions_runtime.py`).
- **LIVE evidence [E]**: none.
- **Cisco-API replacement**: already native.

#### `configureIosDevice(device, iosPayload)` — **PTBUILDER_DEPENDENT**
- **Emitted by [E]**: `shared/ios_config.py:10` (`build_configure_ios_call`),
  reached from 8 generators (`vlan`, `nat`, `acl`, `hardening`,
  `interface_tuning`, `switch_security`, `configuration_renderer`,
  `voice_renderer`), from `ptbuilder_generator.py:175`, from
  `execution/configuration_runtime.py:17`, and from
  `application/use_cases/apply_acl.py:200`.
- **Operations [E]**: all IOS CLI application — VLAN, trunk, ACL, NAT, hardening,
  port security, control plane, voice.
- **Implementation**: **not defined in any tracked file** — **[E]** `grep -rn`
  over `EXTENSION/` finds it only inside `webview/interface.js:1225,1233` as an
  *emitted string* and in `index.html` as documentation.
- **`ipc.*` used**: unknown; the body is PTBuilder's.
- **Offline coverage [E]**: 21 test files — the widest of any symbol.
- **LIVE evidence [E]**: **the only symbol with real LIVE evidence** — 175
  occurrences across 26 files under `docs/reference/cp-scale/**` on the baseline.
- **Cisco-API replacement**: **already exists in production, PTBuilder-free.**
  **[E]** `infrastructure/execution/ios_terminal.py` drives the native terminal:
  `ipc.network().getDevice(name).getCommandLine()` → `enterCommand(...)`,
  `getPrompt()`, `getOutput()`, `getCommandPrompt()`, `isBooting()`. It is
  consumed by 12 modules including `enterprise_configuration_runtime`,
  `enterprise_voice_runtime`, `typed_ping` and four `qualify_*` use cases, and it
  has LIVE evidence (`terminal_kind` / `ios_command_line` in 6 evidence files,
  `getCommandLine` in 2). **[I]** Migrating the remaining `configureIosDevice`
  call sites onto `ios_terminal` removes the largest PTBuilder dependency without
  inventing a single API.

#### `addDevice(name, model, x, y)` (global) — **PTBUILDER_DEPENDENT**
- **Emitted by [E]**: `tool_registry.py:2053` (`pt_add_device`);
  `tool_registry.py:2342` (docstring example of `pt_send_raw`);
  `main.js:261` (internal fallback).
- **Operations [E]**: the `pt_add_device` MCP tool; the `lwAddDevice` fallback.
- **Implementation**: not in any tracked file.
- **Offline coverage [E]**: 4 test files.
- **LIVE evidence [E]**: none in tracked evidence.
- **Cisco-API replacement**: `lwAddDevice` already covers the same intent
  natively, but **[E]** `shared/constants.py:62` records that the two differ —
  *"el addDevice global solo escribe al modelo + canvas físico, no al lógico"*.
  **[I]** replacing it requires deciding whether the physical-canvas write is
  needed; that is an ADR, not a lookup.

#### `addLink(d1, p1, d2, p2, cableString)` (global) — **PTBUILDER_DEPENDENT**
- **Emitted by [E]**: `tool_registry.py:2156` only (`pt_add_link`).
- **Operations [E]**: the `pt_add_link` MCP tool (followed by an exact
  both-endpoint read-back convergence check).
- **Implementation**: not in any tracked file.
- **Offline coverage [E]**: **0** test files match the bare name.
- **LIVE evidence [E]**: none.
- **Cisco-API replacement**: `lwAddLink` is the owned equivalent; the observable
  difference is the cable argument (string vs. 8100-series int). **[E]**
  `settings.py:38-40` documents both forms and warns that the 5th argument is
  mandatory for `addLink`.

#### `allModuleTypes` (global object) — **PTBUILDER_DEPENDENT**
- **Used by [E]**: `main.js:236,343`; `tool_registry.py:2654`
  (`pt_install_modules_batch`, emitted directly into the batch JS).
- **Operations [E]**: `pt_add_module`, `pt_install_modules_batch`,
  `swapLaptopToWireless`, plan module insertion.
- **Offline coverage [E]**: 0 test files.
- **LIVE evidence [E]**: none.
- **Cisco-API replacement**: see `addModule` — the native surface takes an int,
  and the owned catalog already carries one per module.

#### `runCode(js)` — **PTBUILDER_DEPENDENT**
- **Used by [E]**: `EXTENSION/webview/interface.js:59` (the bootstrap snippet
  injected through `window.webview.evaluateJavaScriptAsync`) and
  `interface.js:535` (`$se("runCode", batch)`).
- **Operations [E]**: **the entire HTTP channel.** The file channel does not use
  it — `main.js:137` runs `new Function("reportResult", js)(report)` itself.
- **Implementation**: not in any tracked file.
- **Offline coverage [E]**: 0 test files.
- **LIVE evidence [E]**: 1 mention, in prose, inside
  `docs/reference/cp-scale/canonical_voice_runs.json:2245`
  ("The webview drains queued commands into one runCode batch").
- **Cisco-API replacement**: **[E]** `$se(name, args…)` is a documented Cisco
  built-in (`scriptModules_webViews.htm`) that calls *any* function defined in
  the Script Engine. **[I]** defining our own `runCode` in `main.js`, with the
  same `new Function` + `reportResult` shape already proven by the file channel,
  removes this dependency using only documented mechanisms.

#### `htmlWindow` (constructor) — **PTBUILDER_DEPENDENT**
- **Used by [E]**: `main.js:355` — `window = new htmlWindow();` inside `main()`,
  consumed by `startBridge()` (`window.show()`) and `builder.prototype.menuClicked`.
- **Operations [E]**: showing the MCP Control Center webview — and therefore the
  whole HTTP-channel bootstrap.
- **Implementation**: not in any tracked file.
- **Offline coverage [E]**: 0 test files.
- **LIVE evidence [E]**: none.
- **Cisco-API replacement**: **documented and direct.** **[E]**
  `scriptModules_webViews.htm`: *"The Script Engine has access to the Script
  Module's `webViewManager`"*, with
  `webViewManager.createWebView(title, url, width, height)`, `.show()`,
  `.setUrl()`, `.evaluateJavaScriptAsync(...)`, and the
  `this-sm:Interface0.htm` URL scheme.
- **[I]** This is the single highest-value replacement: it is the one dependency
  that stops `main()` from running at all in a PTBuilder-free module.

#### `getDevices(kind)` — **PTBUILDER_DEPENDENT (non-operational)**
- **Used by [E]**: `tool_registry.py:2341`, inside the `pt_send_raw`
  **docstring** only. No production call site.
- **[I]** Documentation debt, not a runtime dependency.

#### `reportResult(data)` — **OWNED (channel-supplied)**
- **[E]** File channel: `main.js:133-142` injects it as the single parameter of
  `new Function("reportResult", js)`. HTTP channel: `tool_registry.py:1532`
  records *"HTTP: report_result_js define un reportResult que hace XHR a /result"*.
- **Offline coverage [E]**: 6 test files (`test_bridge_results.py`,
  `test_file_bridge_lifecycle.py`, …).

#### `ipc`, `_ScriptModule`, `webViewManager`, `$se`, `$seev`, `$wvca`, `dprint`, `setTimeout`/`clearTimeout` — **CISCO_NATIVE**
- **[E]** Documented in `scriptModules_scriptEngine.htm`,
  `scriptModules_webViews.htm` and `scriptModules_tips.htm` — the last
  explicitly: *"JavaScript's setTimeout(), setInterval(), clearTimeout(), and
  clearInterval() are supported in both the Script Engine and web views"*, which
  is exactly what `main.js`'s file-bridge loop relies on.
- **[E]** `main.js:16` uses `_ScriptModule.unregisterIpcEventByID(...)`; that
  identifier appears in **no** installed help page (unknown #5).

### 3.4 Summary counts

**[E]** 6 symbols `OWNED` (2 of them `OWNED*`), 7 `PTBUILDER_DEPENDENT`
(6 operational + `getDevices`), 1 channel-supplied, the remainder Cisco-native.
**No `UNKNOWN` symbol remains in the emitted set**: every bare global emitted by
Python was traced either to a defining file or proved undefined in tracked source.

---

## 4. PTBuilder dependencies found (TAREA E.4)

**Six runtime dependencies block a PTBuilder-free `.pts` today**, ranked by what
they break:

| # | Symbol | Breaks | Replacement path | Confidence |
| --- | --- | --- | --- | --- |
| 1 | `htmlWindow` | `main()` — the module cannot start | `webViewManager.createWebView` | **documented by Cisco** |
| 2 | `runCode` | the entire HTTP channel | define our own; `$se` is documented | **documented + shape proven** |
| 3 | `configureIosDevice` | all IOS CLI application | `ios_terminal.py` native path, already in production with LIVE evidence | **proven in-repo** |
| 4 | `allModuleTypes` | `addModule`, `swapLaptopToWireless`, module batch | int from owned `ModuleSpec.module_type`; native `isModuleTypeSupported` | **plausible, unvalidated** |
| 5 | `addDevice` | `pt_add_device`; `lwAddDevice` fallback | `lwAddDevice`, if the physical-canvas write is dispensable | **needs an ADR** |
| 6 | `addLink` | `pt_add_link` | `lwAddLink` (cable argument differs) | **needs an ADR** |

**[E]** The six PTBuilder script-engine files are named by the *upstream*
`EXTENSION/script-engine/README.md` at `refactor/cp-live-m0-baseline`:
`userfunctions.js`, `devices.js`, `links.js`, `modules.js`, `runcode.js`,
`windows.js` — *"Reference copies of PTBuilder's script engine, by Kim Knight …
Its repository carries no license, so those files are not redistributed"*.

**[E]** None of the six is present in this checkout: `git ls-files EXTENSION`
lists only `main.js`, the four webview assets, two READMEs and the manifest;
`.gitignore` excludes `EXTENSION/script-engine/*.js` except `main.js`.

**[I]** Mapping the globals onto those filenames — `windows.js`→`htmlWindow`,
`runcode.js`→`runCode`, `modules.js`→`allModuleTypes`, `devices.js`→`addDevice`,
`links.js`→`addLink`, `userfunctions.js`→`configureIosDevice` /`configurePcIp*` /
`addModule` — is an inference from filenames and the upstream README, **not** an
observation. No PTBuilder file was read, obtained or copied.

---

## 5. Packaging contract demonstrated (TAREA C)

### 5.1 Toolchain identity

**[E]** `Get-Item` + `Get-FileHash -Algorithm SHA256`:

```
C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe
FileVersion / ProductVersion : 9.0.1.0858
Length                       : 60005312
LastWriteTimeUtc             : 2026-07-06T16:28:48.0000000Z
SHA-256                      : 843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1
```

This matches the value pinned in `EXTENSION/manifest/muejeje-build-manifest.json`.
**Packet Tracer was not launched.**

### 5.2 Documentation actually read (hashed, not copied)

**[E]** `Get-FileHash -Algorithm SHA256` under
`C:\Program Files\Cisco Packet Tracer 9.0.1\help\default\`:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `scriptModules.htm` | 5505 | `56f0324a5d0ecfe0411e2c7d22d1802c6691ef453b9915dcec0b0ce03e255431` |
| `scriptModules_scriptingInterface.htm` | 9446 | `4bc04309b184ec2f28f8de95762a899a523ae849e462c6c6e4a2069b2d8d1517` |
| `scriptModules_scriptEngine.htm` | 10716 | `d22cafa83f6a4507aaaa948c1c1de233090178ab38b718239717d2748fff4c7e` |
| `scriptModules_tips.htm` | 3232 | `f1b380480801c0349aa3cc8baf2b8b341427a224262381a2d32edcfe418b8b32` |
| `scriptModules_webViews.htm` | 23431 | `2fa1912e2ce5d4025b51dd6d81d4494434323b3971f3610555675902902a8584` |
| `scriptModules_customUdp.htm` | 3612 | `78d972074e310f52c15d64e8f6089402518b3f271170cc3d2f78c43481c09524` |
| `scriptModules_dataStore.htm` | 2592 | `2d540bc3078e2e811f0b6c3999d9ac6b82c067acbb4384a4672e4068d2a5c30e` |
| `scriptModules_data_store_editor.htm` | 2595 | `396156a6967a44a8e261fd9e86452131a96e8937a0956eedda16911475c04159` |

The first five reproduce the previously recorded hashes exactly; the last three
were **not** in the earlier audit and are new to this inventory. `ipc.htm`
(5658 bytes) also exists; the help folder holds 161 files. **Nothing was copied
into the repository.**

### 5.3 The demonstrated procedure

Every row is quoted from the pages above **[E]**:

| Step | Demonstrated fact | Source page |
| --- | --- | --- |
| Create | *"go to Extensions->Scripting->New PT Script Module"* | `scriptingInterface` |
| Manage | *"Add/remove in Extensions->Scripting->Configure PT Script Modules..."* | `scriptModules` |
| Editor | Six parts: Info, General, Script Engine, Custom Interfaces, Data Store, Debug | `scriptingInterface` |
| Module ID | *"The ID should be unique … we recommend using the hierarchical naming pattern, for example: com.yourcompany.scriptModule1"* | `scriptingInterface` |
| Signing | *"PKCS #12 … commonly used to bundle a private key with its X.509 certificate"* | `scriptingInterface` |
| Startup | `On Startup` / `On Demand` / `Disabled`; On Demand triggers = file with save data, a web view loading one of its custom interfaces, or an addressed message | `scriptingInterface` |
| Privileges | *"The security privileges indicate which IPC calls this Script Module can make. Calls to unselected privileges will be denied."* | `scriptingInterface` |
| Engine files | *"add, remove, edit, rename, import, and export script engine files"* | `scriptingInterface` |
| Evaluation order | *"all script files are executed (evaluated) in the Script Engine in the same order as listed in the Scripting Interface"* | `scriptEngine` |
| `main()` | *"When the Script Module starts, it will call the main() function"* | `scriptEngine` |
| `cleanUp()` | *"When the Script Module stops, it will call the cleanUp() function"* | `scriptEngine` |
| Restart semantics | *"Changes made to the Script Engine after it has started DO NOT take effect until it has been stopped and started again."* | `scriptEngine`, `tips` |
| `#include` | *"loads external files inline … the included external files cannot include a reference to another external file. The Script Module only resolves the first level of included external files"* | `scriptingInterface` |
| `#include` at save/export | *"When saving or exporting a Script Module with the #include directive, it will prompt the developer to resolve and expand them inline. This should be done before distributing the pts file"* | `scriptingInterface` |
| Custom Interfaces | *"add, remove, edit, rename, import, and export custom interface files"* — html, css, images, js | `scriptingInterface` |
| Local assets | *"Local resources for custom interface such as images, css, and js files should be imported into the Custom Interface tab. External resources may not be resolved if an absolute path is not supplied."* | `tips`, `webViews` |
| Save → disk | *"Editing a Script Module does not save it to disk until you click on Save in the Scripting Interface for PT Script Modules"* | `tips` |
| Data Store | *"Data store files of all Script Modules are saved in PT options. They are not saved to the pts file unless the user edits the Script Module and saves it to pts file."* | `tips` |
| Encryption | *"PT Script Modules are encrypted .pts files"* | `scriptModules` |
| Sandbox | *"Each Script Module has its own sandbox, and cannot access or change the sandbox of other Script Modules."* | `scriptModules` |
| One engine | *"Each Script Module has one instance of a Qt Script Engine."* | `scriptEngine` |
| WebView URL | `scriptModuleID:customInterfaceID`; `this-sm:Interface0.htm`, `file-sm:…` | `webViews` |
| WebView ownership | pointing a web view at another module's interface **transfers ownership away** | `webViews`, `tips` |

**[E]** Corroborated independently by a read-only ASCII string scan of
`PacketTracer.exe` (no execution): the binary contains
`New PT Script Module ...`, `Configure PT Script Modules ...`,
`Edit File Script Module ...`, `Add Script Module`, `Export Script Module`,
`Export Script Module Translation`, `Script Module List`,
`Script Module starting: `, `Script Module stopping: `,
`The Script Module cannot be started. It is currently disabled.`,
`ExApp or Script Module does not have the necessary privilege for IPC cal…`,
and the file-dialog filter `Script Module File (*.pts)`.

**[I]** How our own sources become a `.pts` is therefore explained end to end:
the five tracked own inputs are imported as Script Engine files (`main.js`) and
Custom Interface files (`index.html`, `interface.js`, `bootstrap.min.css`,
`bootstrap.bundle.min.js`); the General tab supplies ID, startup, privileges and
optional signing; `#include` is resolved at save; **Save** in the Scripting
Interface writes the encrypted `.pts`.

### 5.4 What is NOT demonstrated — no automatable path

**[E]** No packaging CLI exists in the installation:

- `bin\` contains only `PacketTracer.exe`, `QtWebEngineProcess.exe` and Qt
  tooling (`assistant`, `linguist`, `lconvert`, `lrelease`, `lupdate`,
  `meta.exe`, `miniunz.exe`, `minizip.exe`). No script-module builder.
- The long-option strings inside `PacketTracer.exe` are
  `--autoloadptsa`, `--ipc-port`, `--pt-ipc-port`, `--pt-uuid`,
  `--ipc-save-data-id`, `--no-gui`, `--log`, `--progress-bar-server`, plus
  Chromium's `--no-sandbox` / `--remote-debugging-*`. **There is no build,
  export, compile or `.pts` switch.** (`--autoloadptsa` resolves to the
  `ptsaplayer.dll` self-paced-assessment plugin, not to script modules.)
- No help page documents a Packet Tracer command line: the only files matching
  `command[- ]?line` are IOS device-CLI pages (`CLI_router*.htm` etc.).

**[E]** The container is opaque. The first 48 bytes of every shipped module and
template are high-entropy with no `PK` / XML / gzip magic:
`ClearTerminalAgent.pts`, `PcSoftware.pts`, `resource.pts`, `Marvel.pts`,
`PTINTERNAL.pts` and the templates `Chat.ptst`, `StpTree.ptst`,
`PT80Activity.ptst`, `PT601Activity.ptst`, `PcSoftware.ptst`. So are the user's
`PT.conf` and every `logs\pt_*.log`. **[I]** There is no external inspection or
diff route for a built `.pts`; content validation must be behavioural.

**[E]** The IPC API reference is **not installed**: zero `.pki` files anywhere
under the installation, and `scriptModules_scriptEngine.htm` says *"The complete
IPC API reference is located at the Packet Tracer Community. They are declared in
.pki files."*

### 5.5 PACKAGING_CONTRACT_DISCOVERED

**Reached, scoped to the manual GUI procedure.** §5.3 explains, from
vendor-authoritative documentation shipped with the exact pinned build, how our
own sources become a `.pts`: which tab each input goes into, the order the engine
evaluates them in, what `main()`/`cleanUp()` mean, how `#include` is resolved at
save, what metadata (ID, startup, privileges, signing) the module carries, and
that Save writes the file.

**Not reached for automation.** Closing status for that half:

> **`BUILD_TOOLCHAIN_AUTOMATION_UNPROVEN`**

No CLI, no documented programmatic packaging entry point, and an opaque
container. This — rather than `BUILD_TOOLCHAIN_BLOCKED` — is the correct closing
condition, because **no dependency is missing for a manual, auditable build
through the official interface**: §5.3 demonstrates the whole route. Neither
condition is converted into an assumption anywhere in this document.

**Separately, and not to be confused with the gate:** the repository's own
validator currently emits the string `BUILD_TOOLCHAIN_BLOCKED`. **[E]** re-run
this session with the checkout-local interpreter (`sys.executable` and
`packet_tracer_mcp.__file__` both verified inside this worktree, per `AGENTS.md`):

```
.venv/Scripts/python.exe tools/build_muejeje_pts.py --check \
  --builder 'C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe'
BUILD_TOOLCHAIN_BLOCKED        (exit 1)
```

Output was **byte-identical** to the pre-existing `dist/muejeje.build.json`
(diff empty), with `source.commit = e2d912b5…`, `source.tree = 1a5d6453…`
(equal to `git rev-parse HEAD^{tree}`), `source.clean = true`,
`build_recipe_id = null`, `artifact_sha256 = null`, and 8 blockers:

```
unresolved build option: engine_script_order
unresolved build option: custom_interface_order
unresolved build option: module_id
unresolved build option: startup
unresolved build option: privileges
unresolved packaging prerequisite: compiler_command
unresolved packaging prerequisite: content_validation
no compile adapter is implemented for Packet Tracer GUI packaging
```

**[I]** Five of the eight are *decisions not yet made* (§8), and this audit now
supplies the evidence needed to make four of them. `compiler_command` is
unresolvable by construction — there is none.

### 5.6 Version / build used

Packet Tracer **9.0.1.0858**, installed at
`C:\Program Files\Cisco Packet Tracer 9.0.1`, `PacketTracer.exe` SHA-256
`843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1` **[E]**.
The user profile `C:\Users\Andres\Cisco Packet Tracer 9.0.1` contains **no
installed `.pts`** (its `extensions\` directory is empty) **[E]** — so no
currently installed module is at risk from this work, and no stable `.pts` exists
in the working tree (`dist/` holds only the ignored `muejeje.build.json`).

---

## 6. Unknowns (TAREA E.6)

Each is stated as an open question, never as an assumption.

1. **The ordered engine-script list** for a PTBuilder-free module. The evaluation
   rule is known (listed order, then `main()`); our list is not decided.
2. **The Module ID.** Cisco recommends `com.yourcompany.…`; none is chosen and
   `build_options.module_id` is `null`.
3. **The exact privilege set.** Privileges gate IPC calls by name. The full
   privilege catalogue lives in `.pki` files that are **not installed**. Which
   privileges `ipc.systemFileManager()`, `ipc.network()`,
   `ipc.appWindow().getMenuBar()`, `getCommandLine()` and
   `getLogicalWorkspace().addDevice/createLink` require is **unknown**.
4. **Whether the owned `ModuleSpec.module_type` integers equal PT's.** The
   catalog docstring says the numbers are *"que PTBuilder usa internamente"*.
   `device.isModuleTypeSupported(int)` exists to settle it, but that needs LIVE.
5. **`_ScriptModule`**, used at `main.js:16`, appears in no installed help page;
   its contract is unverified.
6. **Whether `webViewManager.createWebView` reproduces `htmlWindow`'s behaviour**
   (sizing, modality, `this-sm:` load, CORS to `127.0.0.1:54321`). Per
   `AGENTS.md`, webview CORS and the `this-sm:` origin **cannot** be established
   offline.
7. **`addDevice` vs `lwAddDevice` semantics.** `constants.py:62` says the global
   also writes the physical canvas; whether anything depends on that is unknown.
8. **Content validation of a built `.pts`.** The container is encrypted and no
   external route exists; validation must be behavioural, under LIVE.
9. **Byte-for-byte reproducibility.** Unknown, and not claimed (§7.3).
10. **Protocol versions for provenance.** No protocol-version constant exists in
    `src/` at all **[E]** — `git grep -nE 'PROTOCOL_VERSION|protocol_version'`
    over `src` and `tests` returns nothing. `PROTOCOL_VERSION = 6` exists only on
    the donor `feature/runtime-protocol-v6-foundation`, which must not be merged.
    So "V5" has **no machine-readable version identifier** to record today.

---

## 7. Provenance schema design (TAREA D) — designed, not built

### 7.1 Gap analysis against the existing report

**[E]** The existing `inspect_build()` report already carries `source.commit`,
`source.tree`, `source.clean`, `inputs.own[].{path,sha256}`, `inputs.reference[]`,
`builder.{name,version,kind,sha256,actual_sha256}`,
`recipe.{extension,output,manifest.sha256,build_options,packaging}`,
`build_recipe_id` and `artifact_sha256`.

| Required by TAREA D | Present today? |
| --- | --- |
| upstream SHA | **missing** |
| source SHA / tree | present |
| extension version | present |
| protocol versions | **missing** (see unknown #10) |
| build recipe ID | present (`null`) |
| own input hashes | present |
| Packet Tracer version / build | present |
| packaging procedure ID | **missing** |
| build options | present (all `null`) |
| artifact SHA-256, external | present (`null`), and correctly kept outside the artifact |

### 7.2 Proposed minimal additions (`schema_version: 2`)

```jsonc
{
  "schema_version": 2,
  "upstream": {
    "branch": "refactor/cp-live-m0-baseline",
    "sha": "e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43",
    "remote_url_id": "<sha256 of the fetch URL>",
    "integration_is_descendant": false,     // measured, never assumed
    "behind": 75, "ahead": 6                 // from rev-list --left-right
  },
  "protocols": {
    "runtime": "v5",                         // literal; no constant exists yet
    "runtime_version_source": "UNVERSIONED_IN_SOURCE",
    "dispatch": null                         // stays null until V6 lands
  },
  "packaging_procedure": {
    "id": "pt-scripting-interface-manual/1",
    "kind": "packet-tracer-scripting-interface",
    "automatable": false,
    "evidence": [
      { "file": "help/default/scriptModules_scriptingInterface.htm",
        "sha256": "4bc04309b184ec2f28f8de95762a899a523ae849e462c6c6e4a2069b2d8d1517" }
      /* … the eight pages of §5.2 … */
    ],
    "steps_digest": "<sha256 of the canonical ordered step list>"
  },
  "build_options": {
    "engine_script_order":    ["EXTENSION/script-engine/main.js"],
    "custom_interface_order": ["EXTENSION/webview/index.html", "…"],
    "module_id": "…",
    "startup": "on_startup",
    "privileges": ["…"],
    "include_resolution": "expanded_inline_at_save",
    "signing": { "used": false, "certificate_sha256": null }
  }
}
```

Invariants the schema must keep, all consistent with the existing implementation:

- `build_recipe_id = recipe_id(recipe)` — canonical JSON, `sort_keys=True`,
  `separators=(",",":")`, `allow_nan=False` — **[E]** already implemented at
  `src/packet_tracer_mcp/infrastructure/pts/build.py:31`.
- The recipe covers upstream + source + manifest + builder identity + procedure
  id + every own/reference input hash + every build option. **An incomplete input
  inventory has no valid complete recipe ID** — the existing code already returns
  `null` while any blocker stands.
- `artifact_sha256` is measured **externally**, after the fact, and is **never**
  embedded inside the artifact it describes.
- `packaging_procedure.automatable` stays `false` until an automation path is
  *demonstrated*, not until one is *hoped for*.

### 7.3 Reproducibility — not claimed, and how to test it

**No byte-for-byte reproducibility is claimed.** **[I]** It is unlikely: the
container is encrypted (§5.4) and Cisco documents no determinism guarantee.

**Proposed experiment `REPRO-2BUILD/1`** — design only. It is **not** executed
here, and executing it needs separate authorization because it launches Packet
Tracer:

1. Freeze the recipe: one commit, `git status` empty, `build_recipe_id` non-null.
2. **Build A** — Scripting Interface → import the ordered inputs → set the
   General tab from `build_options` → Save to `dist/muejeje.pts`. Record
   `artifact_sha256(A)`, the full report, the PT build, and the OS/user context.
3. Restart Packet Tracer. **Build B** — repeat verbatim from the same recipe into
   a distinct path. Record `artifact_sha256(B)`.
4. Compare. Three outcomes, all publishable:
   - `A == B` → `REPRO_BYTEWISE_OBSERVED_N=2` — an observation about this
     builder build only, **not** a general reproducibility claim.
   - `A != B`, both load and pass the same behavioural checks →
     `REPRO_BYTEWISE_REFUTED / REPRO_BEHAVIOURAL_PENDING`; provenance then binds
     one recipe to a *set* of artifacts, each keeping its own hash.
   - Either fails to load → the recipe is incomplete; report the missing option.
5. Optional third arm: the same recipe on a second machine, to separate
   PT-build nondeterminism from host nondeterminism.

Behavioural validation — the only content validation available (§5.4): the module
starts, `main()` runs, the Extensions menu item appears, the file channel writes
`alive.txt` and answers a `req_*.js`, and `cleanUp()` removes the menu item. All
of that is LIVE and out of scope for this unit.

---

## 8. Decisions requiring an ADR (TAREA E.8)

| ADR | Decision | Blocks |
| --- | --- | --- |
| **ADR-1** | Rebase/merge `feature/muejeje-pts` onto `e9e26b3`, or explicitly accept a 75-commit-stale integration branch and advance the watermark | everything; today the branch contradicts its own operating model |
| **ADR-2** | Module ID, and its stability across rebuilds | `build_options.module_id`; PT save data and messaging are keyed by it |
| **ADR-3** | Startup mode (`On Startup` vs `On Demand`) | the file channel only runs while the module runs |
| **ADR-4** | Requested privilege set, and what to do when a needed privilege name is unknown (§6.3) | packaging; a wrong set fails at runtime with denied IPC calls |
| **ADR-5** | Replace `htmlWindow` with `webViewManager.createWebView` | the highest-value PTBuilder removal; unverifiable offline |
| **ADR-6** | Own `runCode` in `main.js` vs keep PTBuilder's | the HTTP channel |
| **ADR-7** | Migrate `configureIosDevice` call sites onto the native `ios_terminal` path | the widest dependency; touches CP-LIVE behaviour, so it must land upstream first per the operating model |
| **ADR-8** | Source `allModuleTypes` from the owned catalog | needs LIVE validation of the integers |
| **ADR-9** | Retire the global `addDevice`/`addLink` in `pt_add_device` / `pt_add_link` in favour of the `lw*` helpers | changes physical-canvas behaviour |
| **ADR-10** | Publisher signing: sign or not; if yes, key custody | `build_options.signing`; affects reproducibility |
| **ADR-11** | Restore the deleted PTBuilder attribution in `EXTENSION/script-engine/README.md` and `.gitignore` while the dependency is real | §2; attribution and licence hygiene |

---

## 9. Existing reusable tests (TAREA E.9)

**[E]** Directly reusable, already present, no PT required:

| Test file | What it already covers |
| --- | --- |
| `tests/test_muejeje_build.py` (445 lines) | manifest schema, blocker aggregation, source clean/dirty, hidden-manifest regression, hardlink/symlink report protection, non-finite JSON |
| `tests/test_muejeje_build_identity.py` (69 lines) | `recipe_id` canonicalization, `artifact_sha256` measurement |
| `tests/test_generators.py` | `lwAddDevice` / `lwAddLink` / `configurePcIp` emission |
| `tests/test_module_port_effect_contract.py` | the `addModule` replay-safe receipt contract |
| `tests/test_injection_regressions.py` | the `json.dumps`-per-field rule (`AGENTS.md` rule 1) |
| `tests/test_bridge_security.py`, `tests/test_bridge_results.py` | HTTP channel + `reportResult` against a real ephemeral-port bridge |
| `tests/test_file_bridge.py`, `tests/test_file_bridge_lifecycle.py` | the file channel end to end |
| `tests/test_worktree_isolation.py` | the `src.` vs bare-import rule |
| `tests/test_e95_architecture_boundaries.py` | layering |
| `tests/test_poe_factory_structure.py` | native `getType` / `isModuleTypeSupported` shapes — the ADR-8 evidence base |
| `tests/test_wireless.py`, `tests/test_ipv6.py`, `tests/test_regressions_runtime.py` | `swapLaptopToWireless`, `configurePcIpv6` |

**Coverage gaps [E]**: `addLink`, `allModuleTypes`, `runCode`, `htmlWindow`,
`getDevices` and `_ScriptModule` have **zero** test references anywhere under
`tests/`. Those are five of the six PTBuilder dependencies — the least-tested
part of the system is exactly the part we intend to replace.

**[E]** No test suite was run in this session; the table above is file
inspection, not a fresh green run.

---

## 10. Proposed new files (TAREA E.10) — proposal only, none created

The only file this unit creates is **this document** (explicitly requested
documentation). Everything below awaits authorization.

| Path | Purpose | Depends on |
| --- | --- | --- |
| `docs/adr/0001-muejeje-integration-base.md` | ADR-1 | — |
| `docs/adr/0002-muejeje-module-identity.md` | ADR-2 / 3 / 4 / 10 | §5.3, §6 |
| `docs/adr/0003-owned-webview-lifecycle.md` | ADR-5 | §4 |
| `docs/adr/0004-owned-runcode-channel.md` | ADR-6 | §4 |
| `docs/adr/0005-native-ios-terminal-migration.md` | ADR-7 | must land upstream first |
| `EXTENSION/manifest/muejeje-build-manifest.json` | **edit** to `schema_version: 2` | §7.2, ADR-2/3/4 |
| `src/packet_tracer_mcp/infrastructure/pts/provenance.py` | upstream + protocols + procedure blocks; recipe assembly | §7.2 |
| `tests/test_muejeje_provenance.py` | red-first tests for the above | `AGENTS.md` rule 5 |
| `docs/qa/muejeje-repro-2build.md` | the `REPRO-2BUILD/1` protocol and its future results | §7.3 + LIVE authorization |

No new `.pts`, no runtime source change, no `mcpDispatchV6`, no CP-LIVE change
and no runtime-evidence change is proposed by this unit.

---

## Closing status

| Gate / condition | Status |
| --- | --- |
| `GOVERNANCE_BASELINED` | **reached** — heads, merge-bases, full delta, source-of-truth ordering and a clean tree are demonstrated (§1, §2) |
| `PACKAGING_CONTRACT_DISCOVERED` | **reached, scoped to the manual GUI procedure** (§5.3, §5.5) |
| `BUILD_TOOLCHAIN_AUTOMATION_UNPROVEN` | **declared** — no CLI, no programmatic entry point, opaque container (§5.4) |
| `BUILD_TOOLCHAIN_BLOCKED` | **not** the task-level condition. The string is emitted today by `tools/build_muejeje_pts.py --check` about 8 unresolved recipe fields, 5 of which are decisions listed in §8 (§5.5) |
| `mcpDispatchV6` | not implemented, not designed here |
| CP-LIVE functionality | unchanged |
| Runtime evidence | unchanged |
| `.pts` built or installed | none |
| LIVE | `NO_LIVE_THIS_SESSION` |
| Push | none |
| PTBuilder files obtained / copied / redistributed | none |
