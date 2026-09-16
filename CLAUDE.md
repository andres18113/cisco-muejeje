@AGENTS.md
@docs/engineering/standards.md

# Claude Code-specific differences

- Claude Code reads `CLAUDE.md`, not `AGENTS.md` directly; the imports above are
  the compatibility boundary and must remain relative to this checkout.
- In a fresh session, run `/context` and confirm this `CLAUDE.md` and both
  imported files are present under memory/context sources before work. If that
  cannot be observed, report instruction loading as pending.
- Plans and task lists are transient aids. The versioned change brief required
  by the imported standard is the durable M/L design and traceability record.
