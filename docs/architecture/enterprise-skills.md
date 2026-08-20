# Enterprise Skills Architecture

This page is a compact companion to
[`skills-governance.md`](skills-governance.md). That document owns policy;
[`skills/manifest.json`](../../skills/manifest.json) owns the canonical project
inventory, lifecycle, consumers, source anchors, support relationships, and
distribution rules. This page describes how the current responsibilities fit
together without redefining either contract.

## Canonical inventory

The manifest contains 17 canonical Skill identities.

Sixteen are ACTIVE:

- planning and sequencing: `enterprise-network-design`,
  `enterprise-ipam-capacity`, `enterprise-hardware`,
  `enterprise-orchestrator`;
- foundational and domain configuration: `enterprise-configuration`,
  `enterprise-services`, `enterprise-voice`, `enterprise-security`;
- control-plane behavior: `campus-layer2`, `first-hop-redundancy`,
  `routing-igp`;
- Packet Tracer and outcomes: `packet-tracer-capabilities`,
  `packet-tracer-layout`, `packet-tracer-runtime`, `network-acceptance`,
  `network-diagnosis`.

`network-autofix` is PLANNED and is excluded from normal distribution. The
deprecated `skill/SKILL.md` compatibility artifact is not a canonical Skill and
has no authority over this inventory.

## Routing model

Each reasoning step has one PRIMARY Skill and zero to two allowed SUPPORTING
Skills. The manifest records the allowed relationships; the task's current
intent determines which relationship is needed.

Use `enterprise-orchestrator` as primary only for a genuinely multi-domain
request that needs classification and sequencing. After classification, one
domain Skill owns the active reasoning step at a time. A handoff changes that
owner; it does not claim that earlier context is physically evicted. Direct
single-domain requests should route to their specialist without activating the
orchestrator.

Capabilities, runtime operation, and typed configuration mechanics can support
a domain owner when the step needs them. Planning outputs normally pass forward
as artifacts rather than keeping every earlier Skill active.

## Control-plane boundary

The shared `ControlPlanePlan`, compiler, applicator, and runtime are source-code
ownership. They do not collapse three agent responsibilities:

- `campus-layer2` owns STP-family and EtherChannel resilience, not routine
  VLAN/trunk plumbing;
- `first-hop-redundancy` owns virtual-gateway roles, forwarding, failover, and
  recovery;
- `routing-igp` owns typed IPv4 IGP behavior for RIPv2, OSPFv2, and EIGRP.

The specialists may read the same implementation seam while retaining distinct
positive intents, negative boundaries, and evidence questions.

## Content and fact ownership

Skills preserve compact operational methodology: responsibility boundaries,
decision flow, hard stops, evidence expectations, and conditional navigation.
They do not reproduce deterministic source behavior or current environment
state.

Current source and tests own implemented types, algorithms, public exposure,
and deterministic behavior. Capability discovery and fresh runtime evidence own
environment-specific support, observability, and results. When a current fact
matters, locate the focal source or test and read it directly; do not rely on a
static capability snapshot or a historical implementation narrative in a
Skill.
