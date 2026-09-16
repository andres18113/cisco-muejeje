# AGENTS.md

This is the shared repository authority for coding agents and maintainers. Read
it before changing the repository. Tool-specific instruction files must import
this file and must not restate its rules.

## Engineering method

Before planning or modifying anything, open and read
`docs/engineering/standards.md` from the current checkout. A Markdown link, an
instruction copied from another checkout, or prior familiarity does not prove
that the current file was read.

The mandatory engineering standard is
[`docs/engineering/standards.md`](docs/engineering/standards.md). It defines the
incremental V-Model, S/M/L risk classification, proportional change brief,
coding and architecture rules, verification order, evidence semantics, and
review boundary. It is incorporated here by reference.

Classify risk and record the change design before implementation. Risk may rise
when new facts emerge; it may not be lowered to avoid a control. Stay within the
approved contract and preserve unrelated or user-owned changes. Do not perform
Packet Tracer LIVE work without explicit authorization for that exact scope.

## Repository authority and collaboration

- `main` contains integrated and accepted work, not experimental development.
- Every task identifies its checkout, branch, and starting SHA before edits.
- Only one active writer may modify a worktree at a time.
- Every worktree owns its `.venv` and editable installation.
- Read instructions from the active worktree, never from another checkout.
- Propagate policy through reviewed Git integration, never by copying files
  between worktrees.
- A Claude/Codex handoff records branch, SHA, pending changes, and completed
  verification.

Prefer sibling worktrees of `Cisco-MCP` when creating future worktrees so parent
instruction inheritance is explicit. Never relocate, delete, or rewrite another
worktree, environment, or unpublished work as incidental cleanup.

## Repository and layers

This MCP server plans and validates Cisco Packet Tracer topologies, generates
Script Engine JavaScript and IOS CLI configuration, and can send commands to a
running Packet Tracer instance through a local bridge.

| Path | Responsibility |
| --- | --- |
| `src/packet_tracer_mcp/domain/` | Models, business rules, and pure planning services |
| `src/packet_tracer_mcp/application/` | Use cases that orchestrate through injected ports |
| `src/packet_tracer_mcp/infrastructure/` | Generators, executors, bridges, persistence, and catalog adapters |
| `src/packet_tracer_mcp/adapters/mcp/` | MCP boundary and tool registration |
| `EXTENSION/script-engine/` | Maintained Packet Tracer Script Engine source and reference material |
| `EXTENSION/webview/` | MCP Control Center webview |

`tool_registry.py` defines tools as closures inside `register_tools()`. A helper
that needs direct testing belongs in the module or layer that owns its behavior,
not inside an unimportable closure.

## Local build and verification

Use the checkout-local virtual environment from the repository root. Do not set
a custom `PYTHONPATH` and do not substitute another checkout's interpreter.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test,docs,quality]"
.\.venv\Scripts\python.exe scripts\quality_gate.py --base cisco/main
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mkdocs build --site-dir _site
git diff --check
```

The command above is provisional while the worktree is dirty. After committing,
validate delivery from a clean tree with
`scripts\quality_gate.py --base cisco/main --delivery-commit HEAD`.

On Linux, use `.venv/bin/python` with the same modules and arguments. CI uses
the same quality entry point and preserves the Windows/Linux × Python 3.11/3.13
pytest matrix.

## Packet Tracer safety constraints

1. Never construct generated JavaScript with raw f-strings. Serialize every
   data field with `json.dumps`; PT executes the result with `new Function()`.
2. Never construct filesystem paths by concatenation. Sanitize external path
   components with `safe_name_component()` and enforce containment with
   `resolve_within()` from `src/packet_tracer_mcp/shared/utils.py`.
3. Never add an unauthenticated HTTP bridge endpoint. Every endpoint except
   `/ping` requires the bridge token. The file mailbox is a separate,
   user-ACL-controlled channel under `%LOCALAPPDATA%`.
4. Keep business validation out of Pydantic models. Domain rules return
   `ValidationResult`; use cases decide whether execution may continue.
5. Preserve the import namespace and LIVE process gate defined below.
6. Never guess a Packet Tracer API signature. Confirm unused methods against
   Cisco's reference before implementation.
7. Apply fail-closed authorization, provenance, retry, error, and evidence rules
   from the engineering standard before any effect.

## Import namespace and LIVE process gate

The target architecture has one identity: `packet_tracer_mcp` in production and
tests. Production code already uses it. The suite's `src.packet_tracer_mcp`
imports are temporary containment for a historical editable-install defect, not
the final architecture. Until the separate
[`namespace migration`](docs/engineering/change-briefs/namespace-migration.md)
is authorized and verified, preserve the current containment and
`tests/test_worktree_isolation.py`; do not create a mixed interval or aliases in
`sys.modules`.

Before any LIVE Packet Tracer mutation, prove all three conditions in the exact
process that will mutate state:

```text
sys.executable              is the checkout-local .venv interpreter
packet_tracer_mcp.__file__  resolves inside the current checkout
sys.modules holds exactly one of packet_tracer_mcp / src.packet_tracer_mcp
```

Loading both namespaces creates distinct classes and enums over the same files;
identity and `isinstance` checks then fail silently. Static tests in another
process do not establish the LIVE process identity.

## Bridge and evidence boundaries

Most verification is offline. Follow `tests/test_bridge_security.py` to exercise
a real `PTCommandBridge` on an ephemeral port, and set `PT_MCP_BRIDGE_TOKEN` so
tests never read or replace the operator's token file.

Offline CI cannot verify Packet Tracer, webview CORS, the `this-sm:` origin, or
Script Engine API reachability. Report those results as unverified until a
separately authorized and observed LIVE run exists. Historical evidence is
immutable. Never infer support or successful execution from documentation,
configuration, an offline test, or an earlier run.

## Packet Tracer execution constraints

- Pasted `executeCode()` source loses newlines; pasted snippets must be one line
  and must not contain `//` comments. Compiled `.pts` JavaScript may be multiline.
- An uncaught `runCode` error opens a modal and stops webview polling. Preserve
  the defensive `try { ... } catch { ... }` boundary for fire-and-forget work.
- Machine-local secrets belong under `%LOCALAPPDATA%`, not roaming `%APPDATA%`.
