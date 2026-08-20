---
name: packet-tracer
description: Use only when maintaining an existing installation that explicitly invokes the legacy packet-tracer companion Skill. This deprecated compatibility artifact points to the governed canonical Skill distribution and is not an operational router, tool catalog, capability source, or authority for new installations.
---

# Packet Tracer MCP compatibility

> **Deprecated compatibility artifact.** This file preserves the `packet-tracer`
> identity for existing manual installations. It is not part of the canonical
> Skill inventory and must not be distributed as an operational Skill.

## Authority

The canonical inventory is [`../skills/manifest.json`](../skills/manifest.json).
Portable operational contracts live under [`../skills/`](../skills/), and client
adapters are projections of those contracts. Project policy is defined in
[`../docs/architecture/skills-governance.md`](../docs/architecture/skills-governance.md).

This compatibility file does not:

- route requests among the canonical Skills;
- define current tools, device support, or runtime capability;
- replace current source, tests, or runtime evidence;
- provide an alternate deployment or mutation procedure.

## Migration

New installations should use the governed export command described in
[`../docs/skill.md`](../docs/skill.md). Existing users should replace this
single-file installation with a fresh projection from the canonical manifest,
then invoke the resulting canonical Skill appropriate to their client and task.

Until migration, use this file only as a pointer to those authorities. Do not
treat it as an operational fallback when a canonical Skill is unavailable.
