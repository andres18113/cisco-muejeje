# Enterprise domain foundation (E1)

E1 introduces a logical layer above the existing topology pipeline. It is additive:
the current `TopologyPlan` remains the concrete representation used to validate,
generate and deploy Packet Tracer artifacts.

```text
EnterpriseIntent
      ↓
EnterpriseDesigner
      ↓
EnterprisePlan
      ↓
[future EnterpriseCompiler]
      ↓
TopologyPlan
      ↓
Existing MCP Pipeline
```

## Intent, requirements, and plans

`EnterpriseIntent` describes the requested company: sites, endpoint requirements,
service requirements, routing preference, and growth. A requirement names a
logical `DeviceRole` such as `IP_PHONE`, `ACCESS_SWITCH`, or `WAN_ROUTER`; it
never names a Packet Tracer model.

`EnterpriseDesigner` validates the intent and creates an `EnterprisePlan` with
`SitePlan` objects and semantic `NetworkSegment` objects. For example, phones
become a `VOICE` segment and cameras a `CCTV` segment. E1 deliberately does not
assign VLAN IDs, subnets, gateways, IOS configuration, or a `TopologyPlan`.
Those deterministic allocations belong to E2.

Validation is kept in `requirements_validator.py`, not in Pydantic models, so
callers receive structured validation results instead of hidden model policy.

### Typed WAN uplinks

`SiteIntent.uplinks` and `SitePlan.uplinks` use `WanLinkRequirement`, whose
peer is a stable `site_id` and whose medium is a `LinkMedia`. The earlier
`SitePlan.uplinks: list[str]` was an unused foundation placeholder: it had no
corresponding `SiteIntent` input, MCP tool, persistence format, documented
meaning, or compiler consumer. It was therefore not a supported serialized
contract, and Stage 3A4 replaces it without legacy-string coercion. Empty
non-WAN plans still serialize `uplinks` as `[]`.

WAN requirements are validated before `EnterprisePlan` creation. A self-link,
an unknown peer, an unknown medium, or contradictory media for the same
undirected site pair returns the normal structured `ValidationResult` and no
plan. There is no Enterprise-plan schema version to bump; the governed
`TopologyPlan.hash_schema_version` contract is unchanged.

## Capabilities and hardware selection

The infrastructure adapter reads the existing Packet Tracer device and module
catalogs, converts physical facts into `CatalogDeviceFacts`, and passes them to
the domain `CapabilityResolver`. The adapter is the only E1 component that
imports Packet Tracer catalog code.

Only facts present in the catalog are asserted: canonical model, aliases,
physical port counts/types, and known compatible modules. Protocol, PoE, voice,
and other logical features have a three-valued `CapabilityStatus`:
`SUPPORTED`, `UNSUPPORTED`, or `UNKNOWN`. Lack of evidence remains `UNKNOWN`.
This is especially important for empty modular chassis: they are represented but
never treated as complete routers or switches.

`DeviceSelector` accepts `DeviceRequirement` plus candidate capabilities. It
filters mandatory port/category/capability constraints, rejects unverified PoE
or Layer-3 requirements rather than guessing, ranks compatible candidates
deterministically, and returns one compact selection with alternatives and
reasons. The future MCP layer can store the full plan server-side and expose
summary/section queries without sending the catalog or an entire plan on every
call.

## E1 boundary

E1 has no MCP tools, bridge calls, Packet Tracer JavaScript, global plan store,
VLSM/IPAM, capacity allocation, services deployment, acceptance tests, or
autofix. It is fully testable offline. The host IP/mask behavior in Packet
Tracer also remains pending live verification; E1 does not alter that runtime
helper.
