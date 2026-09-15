# Cisco-Muejeje

Cisco-Muejeje is a [Model Context Protocol](https://modelcontextprotocol.io) (MCP)
server for Cisco Packet Tracer. It builds typed network plans and validates them.
It generates Packet Tracer Script Engine JavaScript and IOS configuration, applies
both to a running Packet Tracer through a local bridge, and reads the result back.
Claims about what Packet Tracer actually did rest on governed, hash-pinned
evidence kept in this repository.

Repository: <https://github.com/andres18113/cisco-muejeje>

The project started as a fork of
[Mats2208/MCP-Packet-Tracer](https://github.com/Mats2208/MCP-Packet-Tracer). See
[NOTICE.md](NOTICE.md) for provenance and attribution.

## Problem it addresses

Packet Tracer has no external automation API. It offers two programmable surfaces:
its Script Engine, which runs JavaScript inside the application, and the IOS
console of each device. Automating it raises three technical problems:

1. **A consistent intended network.** Devices, modules, ports, cables,
   addressing, VLANs and routing must agree with each other. They must also
   match what the Packet Tracer build supports, before anything is created.
2. **Safe delivery.** Packet Tracer runs generated JavaScript through
   `new Function()`, so an unescaped field becomes code execution. A loopback
   HTTP bridge can be reached by any web page unless it is authenticated.
3. **Evidence rather than assumption.** A command that returns does not show
   that a device reached the intended state. Packet Tracer answers a wrong call
   with a bare `Invalid arguments for IPC call`. Results have to be read back and
   classified, and LIVE runs have to be authorized and cleaned up.

## Architecture

```text
MCP client
   │  stdio, or streamable-http on 127.0.0.1:39000
adapters/mcp        tool and resource registries, public-surface selection
   │
application         use cases, Enterprise pipeline, CP-SCALE / CP-LIVE contracts
   │
domain              Pydantic models, validation rules, planning services (no I/O)
   │
infrastructure      catalog, generators (Script Engine JS, IOS CLI), execution
   │                runtimes, HTTP bridge, file bridge, persistence
   │  HTTP bridge on 127.0.0.1:54321 (token)  ·  file mailbox under %LOCALAPPDATA%
MCP Control Center extension (.pts) → Packet Tracer Script Engine → devices
```

- **Classic path**, inherited from upstream: `TopologyPlan` → validation and
  auto-fix → generated JavaScript and IOS CLI. The output is then deployed live,
  copied to the clipboard or exported.
- **Enterprise path**: `EnterpriseIntent` → `EnterprisePlan` → `HardwarePlan`.
  The Enterprise compiler (E4) turns that into a concrete `TopologyPlan`. Typed
  configuration, services, voice, security and control-plane plans are then
  applied through the Packet Tracer runtime and verified by read-back.
- **Two channels to Packet Tracer.** The HTTP bridge is used while the extension
  window is open. Every endpoint except `/ping` requires a per-machine token. The
  file bridge is used while the window is closed: the Script Engine polls a
  mailbox in a user-owned directory.

Details: [docs/architecture.md](docs/architecture.md) and the records under
[docs/architecture/](docs/architecture/).

## Current capabilities

The registered MCP surface below was measured at this commit by registering the
server in-process:

| Public surface (`PT_MCP_PUBLIC_SURFACE`) | MCP tools | MCP resources |
| --- | --- | --- |
| `enterprise` (default) | 63 | 5 |
| `developer-capability-investigation` | 64 (adds `pt_send_raw`) | 5 |

What is verified, and how:

- **Offline, by the test suite.** This needs no Packet Tracer. CI runs it on
  Windows and Ubuntu with Python 3.11 and 3.13. It covers:
  - topology planning, IP addressing, validation and auto-fix;
  - JavaScript and IOS generation, including injection regressions;
  - bridge authentication;
  - the Enterprise planning and compilation pipeline;
  - typed runtime contracts;
  - Skills governance;
  - the hashes of the CP-SCALE state and evidence documents.
- **Against Packet Tracer `9.0.1.0858`, by governed runs with recorded
  evidence:**
  - Packet Tracer capability discovery, whose reviewed results are projected into
    `infrastructure/catalog/measured_capabilities.py`;
  - RIPv2 replay safety and typed RIPv2 route exchange on `2911`
    ([ripv2-runtime-qualification.md](docs/architecture/ripv2-runtime-qualification.md));
  - EIGRP on `1941`
    ([eigrp-runtime-qualification.md](docs/architecture/eigrp-runtime-qualification.md));
  - the CP-SCALE qualification described under [CP-LIVE status](#cp-live-status).
- **Inherited from upstream.** The classic topology, inspection, simulation,
  canvas and project tools were verified by the upstream project against Packet
  Tracer `9.0.0.0810` (see [CHANGELOG.md](CHANGELOG.md)). Cisco-Muejeje's governed
  qualifications cover only the scopes listed above.

Tool reference: [docs/tools.md](docs/tools.md).

## Installation and running

Requirements:

- Python 3.11 or later.
- For live operation, Windows with Cisco Packet Tracer installed. The governed
  evidence in this repository was recorded on Packet Tracer `9.0.1.0858`.

Planning, validation, generation and the test suite do not need Packet Tracer.

```bash
git clone https://github.com/andres18113/cisco-muejeje.git
cd cisco-muejeje
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"   # Windows
.venv/bin/python -m pip install -e ".[test]"           # Linux / macOS
```

Run the test suite from the repository root with the checkout-local interpreter.
[AGENTS.md](AGENTS.md) explains why the interpreter matters.

```bash
.venv/Scripts/python.exe -m pytest -q   # Windows
.venv/bin/python -m pytest -q           # Linux / macOS
```

Start the server with the interpreter of the environment it is installed in:

```bash
python -m packet_tracer_mcp --stdio   # stdio, for desktop MCP clients
python -m packet_tracer_mcp           # streamable-http on 127.0.0.1:39000
```

The `pt-mcp` console script is equivalent. To register the server with an MCP
client, for example Claude Code:

```bash
claude mcp add --scope user --transport stdio packet-tracer -- python -m packet_tracer_mcp --stdio
```

In Windows PowerShell, quote the separator as `"--"`; otherwise PowerShell
consumes it. Other clients are covered in
[docs/installation.md](docs/installation.md).

### Packet Tracer extension

Live operation needs the MCP Control Center extension loaded in Packet Tracer:

1. Add the `.pts` module with **Extensions → Scripting → Configure PT Script
   Modules → Add…**.
2. Open **Extensions → MCP BUILDER**.

The extension source is in [`EXTENSION/`](EXTENSION/). Cisco-Muejeje does not
publish a compiled `.pts`. Building one needs PTBuilder reference files that this
repository does not redistribute; see
[EXTENSION/script-engine/README.md](EXTENSION/script-engine/README.md). The
upstream project published a compiled module, `V5.2.pts`, with its
[releases](https://github.com/Mats2208/MCP-Packet-Tracer/releases). The server
rejects extension builds older than V5, because they do not send the bridge
token.

### Governed Skills

[`skills/manifest.json`](skills/manifest.json) is the canonical Skills inventory.
Export a client projection into a directory that does not exist yet:

```bash
python -m tools.skills_governance export --destination .skill-staging-claude --audience operation --client claude
```

[docs/skill.md](docs/skill.md) describes how to replace an existing installation.

## CP-LIVE status

CP-LIVE is the governed path that executes the Enterprise product chain against a
real Packet Tracer. It targets the CP-SCALE reference design, which has three
sites and 279 workload endpoints; see
[cp-scale-qualification.md](docs/architecture/cp-scale-qualification.md).
[`docs/reference/cp-scale/current_state.json`](docs/reference/cp-scale/current_state.json)
is the authority for its state, and
[`docs/reference/cp-scale/README.md`](docs/reference/cp-scale/README.md) indexes
the evidence. The evidence files are immutable and hash-pinned, and tests check
those hashes.

| Target | Closure | Executed at |
| --- | --- | --- |
| `router0-branch` | `ROUTER0_BRANCH_VERIFIED_AND_CLEANED` | `8980ada7ab993cbe5b5b915cefde24deb04b3e3f` |
| `router3-branch` | `ROUTER3_BRANCH_VERIFIED_AND_CLEANED` | `d2245d45d442d32f5dfb107b1a715089f1cb8551` |
| `full-qualification` | `CP_SCALE_FULL_QUALIFICATION_VERIFIED_AND_CLEANED` | `6a80b24626d40fb59bad5f0dc2e47d18a51f4a49` |

- **Full qualification.** Run
  `canonical-cp-scale-voice-20260915T193037865890Z-6a80b24626d4` built the seven
  stages from an empty workspace. It then ran `remaining` as the terminal stage,
  with a zero physical delta. It proved forwarding for the three declared site
  pairs in both directions, and its closure was published only after a verified,
  attested cleanup. Its success index is
  [`full_qualification_successful_run.json`](docs/reference/cp-scale/full_qualification_successful_run.json),
  SHA-256 `1ff5eb92331ad4f13e3780b31d7fba0b991942e2176989b6669940662f1a5011`.
- **Earlier failed run.** A full-qualification run executed at
  `ff117655a97301aa05cad6c7696f89dd87ec71fc` FAILED at `floor3` when the Packet
  Tracer process crashed. It remains FAILED, and the later success does not
  reinterpret it.
- **Qualified scope.** The backend policy for Packet Tracer `9.0.1.0858`
  qualifies voice configuration, phone registration and extension binding. Call
  behaviour and wireless association are unqualified, intersite calling is off,
  and none of them is a full-qualification criterion. The latest
  call-observability attempt was BLOCKED; it is diagnostic only.
- **Current state.** `next_active_step` is
  `CP_LIVE_CLOSED_BY_VERIFIED_FULL_QUALIFICATION` and `live_execution_authorized`
  is `false`. No re-execution is authorized. Every canonical target is refused
  before contacting Packet Tracer unless an explicit authorization names both the
  target and the exact source SHA.

## Relationship with Packet Tracer

- Packet Tracer is not included and must be installed separately. Cisco-Muejeje
  is not affiliated with Cisco.
- The server reaches Packet Tracer only through the extension. Commands run in
  the Script Engine, and IOS configuration reaches devices through it.
- Packet Tracer API behaviour is version-specific. A wrong call fails without
  saying why, so [AGENTS.md](AGENTS.md) requires any API call not already used in
  the repository to be confirmed against Cisco's reference first. The governed
  qualification records name the Packet Tracer build they measured.
- Offline tests cannot verify the webview behaviour: CORS, the `this-sm:` origin,
  and what the Script Engine can reach.

## Limitations

- No compiled `.pts` is published by this repository, and building one requires
  PTBuilder files that are not redistributed.
- The file bridge does not guarantee exactly-once or at-most-once execution
  (`TD-TRANSPORT-001` in
  [technical-debt.md](docs/architecture/technical-debt.md)).
- Offline tests do not establish Packet Tracer behaviour. Statements about
  Packet Tracer are limited to the scopes of the governed evidence.
- Call behaviour and wireless association are unqualified, and intersite calling
  is off.
- Live operation is Windows-oriented: Packet Tracer, `%LOCALAPPDATA%` for the
  token and mailbox, and `clip.exe` for the clipboard.
- On the developer surface, `pt_send_raw` executes arbitrary JavaScript inside
  Packet Tracer.
- The inherited technical names are unchanged, because they are compatibility
  contracts; renaming them is a separate migration:
  - the Python package `packet_tracer_mcp`;
  - the distribution `packet-tracer-mcp`;
  - the console script `pt-mcp`;
  - the MCP server name `Packet Tracer MCP`;
  - the state directory `%LOCALAPPDATA%\packet-tracer-mcp`.
- The package version, `0.8.0`, is inherited from upstream. No Cisco-Muejeje
  release has been tagged.
- Some pages under `docs/` still describe upstream-era behaviour and counts,
  such as the classic tool guides and `docs/testing.md`.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/packet_tracer_mcp/domain/` | Pydantic models, validation rules, planning services |
| `src/packet_tracer_mcp/application/` | Use cases, Enterprise pipeline, CP-SCALE / CP-LIVE contracts |
| `src/packet_tracer_mcp/infrastructure/` | Catalog, generators, execution runtimes, HTTP and file bridges, persistence |
| `src/packet_tracer_mcp/adapters/mcp/` | MCP tool and resource registries, public-surface selection |
| `src/packet_tracer_mcp/shared/` | Shared helpers such as escaping and path containment |
| `EXTENSION/` | Packet Tracer extension source: `script-engine/main.js` and `webview/` |
| `skills/` | Governed Skills and their manifest |
| `skill/` | Deprecated single-file Skill, kept for compatibility |
| `tools/` | Governed LIVE qualification runners and the Skills governance CLI |
| `tests/` | Offline test suite |
| `docs/` | MkDocs sources, architecture and qualification records, QA notes, design plans |
| `docs/reference/cp-scale/` | CP-SCALE state and immutable LIVE evidence |
| `handoff.md` | Legacy CP-SCALE state projection, read by tests |
| `handoff_github_corrections.md` | Non-authoritative continuity note |
| `AGENTS.md` | Rules for coding agents working in this repository |

## Security

The HTTP bridge:

- binds to `127.0.0.1`;
- requires a per-machine token on every endpoint except `/ping`;
- validates `Host` against loopback;
- caps request body size.

The file bridge uses a mailbox in a user-owned directory under `%LOCALAPPDATA%`.
[SECURITY.md](SECURITY.md) documents the threat model and how to report a
vulnerability.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License and attribution

MIT. [LICENSE](LICENSE) keeps the upstream copyright notice unchanged.

- **Upstream project:** [Mats2208/MCP-Packet-Tracer](https://github.com/Mats2208/MCP-Packet-Tracer),
  by Mateo ([@Mats2208](https://github.com/Mats2208)), distributed under MIT.
  Cisco-Muejeje diverged from it at commit `b075961`.
- **PTBuilder:** [kimmknight/PTBuilder](https://github.com/kimmknight/PTBuilder),
  by Kim Knight ([@kimmknight](https://github.com/kimmknight)), was the historical
  reference for the Script Engine helper surface. Its files are not
  redistributed.
- **Dependencies:** the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
  and [Pydantic](https://docs.pydantic.dev).

Details: [NOTICE.md](NOTICE.md) and [docs/credits.md](docs/credits.md).
