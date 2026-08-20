# Skills governance

This document is the canonical project-governance contract for repository
Skills. It governs authority, precedence, lifecycle, ownership, routing,
progressive disclosure, distribution, client adapters, drift, future
verification, and migration safety. Per-Skill lifecycle and ownership records
live in the machine-readable inventory; this document remains their governing
policy and does not change the portable Agent Skill format.

## Authority and truth

The project keeps distinct authorities:

1. Current governance records own project policy and phase ordering.
2. Current source and tests own implemented product truth.
3. Current runtime and capability evidence own observable capability state and
   its claim ceilings.
4. Skills orchestrate those authorities. They do not redefine, weaken, or
   replace them.

Graphify is a focal navigator. It locates relevant relationships but does not
prove an implementation, policy, dependency, capability, or runtime result.
Every material conclusion must be confirmed against its current authority.

Historical milestones, handoff history, logs, benchmarks, and prior live runs
remain evidence of what happened in their recorded scope. They are not, by
themselves, current implementation or capability evidence.

When Skill prose conflicts with current implementation, `SKILL_DRIFT` is the
default diagnosis. The Skill cannot be used to reinterpret the implementation
as matching its prose.

## Portable contract, project governance, and client adapters

Three layers remain separate:

- **Portable Agent Skill contract:** the agent-neutral `SKILL.md` semantics,
  portable frontmatter, instructions, and targeted references.
- **Project governance:** this repository's lifecycle, ownership, routing,
  authority, evidence, public-surface, distribution, verification, and
  migration rules.
- **Client adapter:** client-specific display, prompting, invocation policy,
  and tool or dependency metadata.

Portable Skill semantics remain agent-neutral. Project governance must not be
encoded as client-specific behavior, and a client adapter must not become a
second source of project truth. Project-specific lifecycle, consumer,
responsibility, source-anchor, support, and distribution records stay outside
portable `SKILL.md` frontmatter.

## Canonical authority and precedence

`skills/` is the canonical logical operational Skill root.

`skill/SKILL.md` is a DEPRECATED, non-authoritative compatibility artifact for
existing manual installations. It is not a router and is never a source for
canonical distribution. Its presence does not give it precedence over
`skills/`, governance, source, tests, or runtime evidence.

Two independently maintained operational Skill authorities are invalid.
Client-specific installations and compatibility artifacts may project or wrap
the canonical logical inventory, but they cannot establish an independent
operational authority.

## Machine-readable inventory

`skills/manifest.json` is the canonical machine-readable inventory. JSON keeps
validation and distribution on the Python standard library; the project does
not declare a YAML dependency. The manifest owns project governance only. It
does not duplicate portable descriptions, capability matrices, runtime
observations, tool catalogs, or Packet Tracer inventory facts.

Each entry records canonical identity and path, lifecycle, consumer, one
primary responsibility, stable source anchors, allowed same-step supporter
sets, and distribution mode/audiences. Eligibility is derived from lifecycle,
consumer, mode, and audience rather than stored as another mutable boolean.
An anchor marked `negative_boundary` identifies adjacent current behavior that
must not be mistaken for implementation of the Skill's responsibility.
Each supporter set contains at most two Skills; multiple sets represent
alternatives, not simultaneous recursive loading.

`skills/routing-evals.json` preserves positive and near-miss routing cases for
later behavioral evaluation. Fixture completeness is mechanically validated;
the fixtures do not prove that a client will trigger a Skill correctly.

## Lifecycle

Every governed Skill has exactly one lifecycle state:

- **ACTIVE:** eligible for normal governed routing and distribution. An ACTIVE
  Skill may operate over capabilities that are `PARTIAL`, `UNOBSERVABLE`, or
  `UNKNOWN`; ACTIVE describes the Skill, not capability support.
- **PLANNED:** records future responsibility but must not advertise or route as
  currently executable.
- **DEPRECATED:** still recognized during an explicit transition, but must not
  normally implicit-route. It requires explicit replacement or removal
  criteria.
- **RETIRED:** no longer operationally distributed or routed.

Lifecycle state and capability-evidence state are orthogonal. Neither ACTIVE
nor any other lifecycle value promotes capability evidence, and capability
evidence does not select a lifecycle state by itself.

## Ownership

One ACTIVE Skill owns one primary operational responsibility. That
responsibility must be distinguishable through positive routing cases and
meaningful negative boundaries.

Shared source models, plans, compilers, applicators, or runtime objects do not
mechanically require a Skill merge. Source structure is evidence about product
ownership, not a replacement for responsibility and routing analysis.

A supporting Skill adds a distinct transversal responsibility, such as runtime
operation or evidence handling. It cannot override the primary owner's domain
decision, current governance, implemented contracts, or evidence ceilings.

An orchestrator owns request classification, sequencing, handoffs, and result
composition. It does not become the primary owner of every domain it
coordinates.

## Routing

For each reasoning or work step, the project-governance target is:

```text
1 PRIMARY + 0-2 SUPPORTING
```

The target applies per step, not necessarily once for an entire multi-domain
request. When more domains are required, they must normally be sequenced
through explicit handoffs rather than eagerly loaded together.

Routing is based on intent and operational responsibility, not filename,
source adjacency, or historical milestone. Every route requires positive
cases and meaningful near-miss negative cases. Persistent ambiguity between
candidate primary Skills is a governance defect.

The `1 PRIMARY + 0-2 SUPPORTING` rule is project governance. It is not a native
Agent Skills, Codex, Claude, or other client-runtime guarantee. Client adapters
and future verification may help enforce it, but must not misrepresent it as a
built-in runtime property.

## Progressive disclosure

The canonical loading order is:

```text
minimal global governance
-> routing/catalog metadata
-> primary SKILL.md
-> 0-2 supporting SKILL.md
-> targeted references
-> focal Graphify
-> exact source/tests
```

References load only when required to answer the current responsibility,
runtime assumption, evidence question, or boundary. Recursive loading of a
reference tree is not the default. Graphify remains a locator; exact source,
tests, governance, and runtime evidence retain their respective authority.

## Public surface and raw compatibility

Normal enterprise Skills must never expose, teach, recommend, or depend on any
of the following as a normal operational fallback:

- raw IOS;
- raw JavaScript;
- `pt_send_raw`;
- `PT_MCP_PUBLIC_SURFACE=developer-capability-investigation`.

The explicit developer compatibility surface is development-only, untyped
compatibility. It is not a typed enterprise capability, normal operational
fallback, runtime-verification shortcut, or enterprise capability evidence.

All Skills preserve `UNKNOWN`, `PARTIAL`, `UNOBSERVABLE`, and every governed
evidence ceiling. Missing, stale, indirect, developer-only, or weaker evidence
must not be promoted to a stronger state.

## Current implementation, exposure, and evidence

Every capability statement keeps three dimensions independently visible:

| Dimension | Governed values |
| --- | --- |
| Implementation | `IMPLEMENTED` or `PLANNED` |
| Exposure | `GOVERNED_TYPED_PUBLIC`, `INTERNAL_ONLY`, or `DEVELOPER_ONLY_COMPATIBILITY` |
| Evidence | `VERIFIED/OBSERVED`, `PARTIAL`, `UNOBSERVABLE`, or `UNKNOWN` |

No Skill may collapse those dimensions into an unsupported `SUPPORTED` claim.
For example, implemented internal code is not necessarily publicly exposed;
public exposure is not runtime verification; and an ACTIVE Skill may correctly
report UNKNOWN evidence.

## Dynamic facts

Version, model, module, port, runtime, capability, and tool-registry facts must
come from their current canonical source, current runtime, or governed
generated evidence.

Skills own the retrieval and interpretation methodology. They do not own
manually duplicated live inventories. A static example or historical result
cannot silently become a current universal fact.

## Distribution

The project has one canonical logical Skill inventory. Client installations
are projections of that inventory, not second authorities.

Normal operational distribution includes eligible ACTIVE operational Skills:

- ACTIVE Skills are eligible for normal distribution.
- PLANNED and RETIRED Skills are excluded.
- DEPRECATED Skills are explicit-only when a client can enforce that safely;
  otherwise they are excluded from normal distribution.

`python -m tools.skills_governance export` produces deterministic projections
to an explicit, absent staging destination. Selection is derived from
lifecycle, audience, and distribution mode; the exporter never reads the
deprecated companion. Portable and Claude projections exclude client adapters,
while the OpenAI projection adds only each selected Skill's
`agents/openai.yaml`. Generated output is not another canonical tree.
Installing an updated projection must replace matching project-managed Skill
directories rather than overlay them, so deleted references and suppressed
lifecycles cannot survive; unrelated user Skills must remain untouched.

## Client adapters

`agents/openai.yaml` is an OpenAI-specific client adapter. It must not own
canonical:

- lifecycle;
- domain responsibility;
- capability truth;
- evidence ceilings;
- project ownership.

Client adapters may control display, prompts, invocation policy, and
client-specific tool or dependency metadata. Those settings must remain a
projection of portable Skill semantics and project governance.

## Drift classes

- **SKILL_DRIFT:** portable Skill prose, responsibility, routing boundary, or
  workflow conflicts with current governance or implementation. This is the
  default diagnosis when Skill prose conflicts with current implementation.
- **ADAPTER_DRIFT:** client-specific metadata, prompts, identity, invocation
  policy, or dependencies conflict with the canonical Skill or project
  governance.
- **DISTRIBUTION_DRIFT:** an installed or published projection differs from the
  eligible canonical inventory, lifecycle policy, identity, or precedence.
- **CAPABILITY_DRIFT:** Skill or adapter capability statements differ from the
  current canonical source, runtime observation, capability evidence, or claim
  ceiling.

The more specific classes may refine a finding after evidence identifies its
seam; they do not let Skill prose override current implementation.

## Verification contract

Automated governance must cover:

- portable format and frontmatter validity;
- lifecycle validity;
- unique primary ownership;
- validity of `1 PRIMARY + 0-2 SUPPORTING` relationships;
- positive and near-miss negative routing cases;
- PLANNED and DEPRECATED routing suppression;
- raw/public-surface safety;
- source-anchor validity;
- current/planned separation;
- preservation of evidence ceilings;
- distribution consistency;
- adapter/canonical identity consistency;
- reference integrity;
- visibility of context-cost regressions.

`python -m tools.skills_governance validate` implements deterministic
repository checks, and `python -m tools.skills_governance metrics` reports
context measurements. The legacy no-subcommand invocation still validates.
Those checks prove structure and consistency, not semantic routing quality or
current runtime capability.

## Phase 4 behavioral closure

The Skills governance restructuring is closed. Authenticated fresh-client
evidence, the 26-scenario NEW matrix, the bounded OLD comparison, the one
ordinary routing defect and its successful rerun, token/context observations,
process-ownership evidence, validation results, and claim limits are recorded
in
[the Phase 4 behavioral closure](skills-governance-phase4-closure.md).

This closure establishes semantic routing behavior for the governed Skill
projection. It does not establish Packet Tracer runtime capability, alter an
evidence ceiling, close E9.5, change the governed CP3-HARD result, or make E10
startable.

## Migration safety

No rename, merge, split, deprecation, or deletion is justified by a Phase-1
smell or shared source object alone. Before such a change, the record must
contain evidence appropriate to the operation:

| Operation | Required evidence before the operation |
| --- | --- |
| Rename | Canonical identity, routing, consumer, adapter, distribution, reference, and compatibility impact; the new identity must preserve responsibility and evidence boundaries. |
| Merge | Sustained responsibility/routing overlap, ambiguous primary ownership demonstrated by positive and near-miss cases, context-cost impact, and proof that distinct transversal boundaries will not be lost. |
| Split | Multiple independently routable primary responsibilities, distinct positive and negative cases, supporting relationships, source anchors, and context-cost evidence. |
| Deprecate | Explicit reason, replacement or removal criteria, routing suppression behavior, affected consumers/adapters/distribution, and a bounded transition condition. |
| Delete | Prior lifecycle and migration record, satisfied retirement/removal criteria, no remaining governed route or distribution eligibility, and accounted consumers, adapters, references, and historical evidence. |

Migration evidence informs a later governed decision. Recording the evidence
does not itself authorize the operation.
