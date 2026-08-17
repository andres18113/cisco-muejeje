# AGENTS.md

Notes for coding agents working in this repo. Read this before changing anything
under `src/`.

## What this is

An MCP server that automates Cisco Packet Tracer. It plans network topologies,
validates them, generates JavaScript for PT's script engine and IOS CLI config
for the devices, and can push all of it into a running copy of Packet Tracer over
a local HTTP bridge.

## Build and test

```bash
pip install -e ".[test]"
./.venv/Scripts/python.exe -m pytest     # from the repo root, no PT required
```

Run the suite with the **checkout-local `.venv` interpreter**, not with whatever
`python` resolves to on `PATH`. Measured on the current machine, a bare `python`
is a different installation with no `pytest` and no editable install, so
`python -m pytest` fails outright. Only the local `.venv` reproduces the governed
baseline. No custom `PYTHONPATH` — `pyproject.toml` sets `pythonpath = ["."]`.

There is no linter or formatter configured. Match the surrounding style: type
hints on public functions, `from __future__ import annotations` at the top,
comments in Spanish or English following whatever the file already uses.

## Layout

| Path | What lives there |
| --- | --- |
| `src/packet_tracer_mcp/domain/` | Pydantic models, validation rules, planning services |
| `src/packet_tracer_mcp/application/` | Use cases: rules + generators, dependencies injected |
| `src/packet_tracer_mcp/infrastructure/` | Generators, executors, the HTTP + file bridges, device catalog |
| `src/packet_tracer_mcp/adapters/mcp/` | `tool_registry.py` — the 61 MCP tools |
| `EXTENSION/script-engine/` | Script-engine side of the extension. `main.js` is ours (tracked); the rest are PTBuilder reference copies (gitignored) |
| `EXTENSION/webview/` | The MCP Control Center webview (`index.html` + `interface.js`) |

`tool_registry.py` is ~3000 lines and every tool is a closure inside
`register_tools()`. That means helpers defined there **cannot be imported by
tests**. If you write a helper worth testing, put it in `shared/utils.py`.

## Rules that are not negotiable

1. **Never build JavaScript with raw f-strings.** Use `json.dumps` for each
   field. PT runs it through `new Function()`, so an unescaped device name is
   arbitrary code execution. `ptbuilder_generator.py` shows the correct pattern.
2. **Never build a path by concatenation.** Use `safe_name_component()` then
   `resolve_within()` from `shared/utils.py`.
3. **Never add an unauthenticated bridge endpoint.** Everything except `/ping`
   requires the token; see `bridge_token.py` for why loopback alone is not a
   control. (The file-bridge channel needs no token — the mailbox lives under a
   user-ACL'd `%LOCALAPPDATA%` dir a browser page can't reach.)
4. **Don't validate in the models.** Validation belongs in `domain/rules/` and
   returns `ValidationResult`, so the use case decides whether to proceed.
5. **A bug fix needs a test that fails without it.** Write the failing test
   first; if it passes before your change, it isn't testing the bug.
6. **Never guess a PT API signature.** If a method isn't already used somewhere
   in this repo, confirm it against Cisco's reference before writing code on top
   of it — PT answers a wrong call with a bare `Invalid arguments for IPC call
   "X"`, so a guess fails without telling you why.

## Import namespace, and the live-run gate

Two namespaces, two contracts. `packet_tracer_mcp` is the **production** name
(the `pt-mcp` console script and `python -m` use it); `src.packet_tracer_mcp` is
the **test** name. New production code must never import the `src.` form.

Tests import `src.packet_tracer_mcp`; run the suite with the checkout-local
`.venv` interpreter from the repo root and no custom `PYTHONPATH`.
`pyproject.toml` sets `pythonpath = ["."]`.

A bare `import packet_tracer_mcp` in a test is a bug, and
`tests/test_worktree_isolation.py` fails on it.

**Which interpreter you use decides which tree you get.** Measured on this
machine, from a worktree root:

| Interpreter | bare `import packet_tracer_mcp` |
| --- | --- |
| worktree-local `.venv` | resolves **inside the worktree** — correct |
| main checkout `.venv` | resolves to the **main checkout** — wrong tree, silently |
| bare `python` on `PATH` | `ModuleNotFoundError`, and no `pytest` either |

So a worktree's own `.venv` is the thing that makes the production namespace
resolve locally. Do not "fix" this by editing another checkout's `.pth`, and do
not install into `PATH` Python to make a shorthand command work.

**Before any live Packet Tracer mutation**, prove all three *in the process that
will perform the mutation*:

```text
sys.executable              is the checkout-local .venv interpreter
packet_tracer_mcp.__file__  resolves inside the tree you are testing
sys.modules holds exactly ONE of packet_tracer_mcp / src.packet_tracer_mcp
```

The third is not theoretical. When one process holds both, they are distinct
module objects over the *same files*, so `CapabilityStatus.SUPPORTED is
CapabilityStatus.SUPPORTED` is **False** across them and every `isinstance` and
enum comparison silently misfires. A passing static isolation test does not
establish any of this for a live process — it runs in a different one.

## Working with the bridge

The bridge only really works with Packet Tracer open, so most verification is
offline. `tests/test_bridge_security.py` drives a real `PTCommandBridge` on an
ephemeral port — follow that pattern rather than mocking HTTP.

Set `PT_MCP_BRIDGE_TOKEN` to avoid touching the user's real token file.

Anything involving PT's webview (CORS behaviour, the `this-sm:` origin, whether
the script engine can reach an API) **cannot be verified from tests**. Say so
explicitly instead of assuming; don't claim a change is verified when only the
offline half was.

## Gotchas

- PT's `executeCode()` **strips newlines** from source that is *pasted* into the
  Builder Code Editor, so any such snippet must be a single line without `//`
  comments. (The compiled `.pts` files — `main.js` etc. — are not pasted and can
  be normal multi-line JS.)
- An uncaught error inside `runCode` opens a modal that freezes the webview and
  kills the polling loop. That is why fire-and-forget commands are wrapped in
  `try{...}catch{}`.
- `%LOCALAPPDATA%`, not `%APPDATA%`, for machine-local secrets — the latter
  roams.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
