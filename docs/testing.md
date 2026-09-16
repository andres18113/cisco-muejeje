# Testing

The suite runs offline. It needs no Packet Tracer and no network, and it covers
the domain, application and infrastructure layers, the MCP surface, and the
integrity of the CP-SCALE state and evidence documents.

## Running the suite

Run pytest from the repository root with the checkout-local interpreter. That
interpreter is what makes the production namespace resolve inside the checkout:

```bash
.venv/Scripts/python.exe -m pytest -q   # Windows
.venv/bin/python -m pytest -q           # Linux / macOS
```

`AGENTS.md` records why the interpreter matters and which import namespace the
production and test sides use.

## Continuous integration

`.github/workflows/tests.yml` runs the same suite on every push, on
`windows-latest` and `ubuntu-latest`, with Python 3.11 and 3.13. The checkout is
full depth on purpose: the CP-LIVE M0 oracle verifies the provenance of its
expected values against the commit object it characterised, and a shallow
checkout does not contain that commit.

The workflow also runs two non-matrix jobs on the same commit: `quality` invokes
the incremental Ruff lint/format entry point and `docs` builds the MkDocs site.
Run their local equivalents with the checkout interpreter:

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py --base origin/main
.\.venv\Scripts\python.exe -m mkdocs build --site-dir _site
git diff --check
```

The quality gate covers complete new and changed Python files. Repository-wide
legacy debt is intentionally outside this incremental boundary; see the
[engineering standard](engineering/standards.md) for the normative policy.

## What is covered

- Topology planning, IPv4 and VLSM addressing, and DHCP pool generation.
- Plan validation with typed error codes, and the auto-fixer.
- Generators: Script Engine JavaScript and IOS CLI, including adversarial
  injection regressions.
- The Enterprise pipeline: designer, IPAM and capacity, hardware planning,
  compiler and layout, configuration, services, voice, security and control
  plane.
- Typed runtime contracts, transport containment, and evidence composition.
- Bridge security, driven against a real `PTCommandBridge` on an ephemeral port
  rather than a mocked HTTP layer: token checks, `Host` validation and body
  limits.
- The hashes and closure state of the CP-SCALE documents under
  `reference/cp-scale/`.

## What the suite cannot establish

- Anything that depends on Packet Tracer itself. Behaviour inside Packet Tracer
  is established only by governed runs, recorded under `reference/cp-scale/` and
  in the qualification records under `architecture/`.
- Webview behaviour: CORS, the `this-sm:` origin, and what the Script Engine can
  reach from inside Packet Tracer.

The unit tests do not start the MCP server. To check that the server boots with
the installed dependencies, run `python -m packet_tracer_mcp --stdio`. It should
start without errors.
