# Governed Agent Skills

The repository provides 17 portable Agent Skill contracts under [`skills/`](../skills/).
[`skills/manifest.json`](../skills/manifest.json) is the single machine-readable inventory for
lifecycle, consumer, responsibility, support relationships, and distribution. Portable `SKILL.md`
files remain client-neutral; client metadata is applied only while exporting a projection.

The old [`skill/SKILL.md`](../skill/SKILL.md) file is a DEPRECATED compatibility artifact for
existing manual installations. It is not a router, capability source, tool catalog, or canonical
operational authority. New installations must use the manifest-driven exporter.

## Export a projection

Run from the cloned repository root. Every export requires a new, explicit staging destination and
validates the canonical inventory before writing. Normal projections contain eligible ACTIVE
Skills for the requested audience; PLANNED and RETIRED Skills are suppressed.

=== "Claude Code"

    ```bash
    python -m tools.skills_governance export --destination .skill-staging-claude --audience operation --client claude
    skill_root="$HOME/.claude/skills"
    mkdir -p "$skill_root"
    for source in .skill-staging-claude/skills/*; do
        target="$skill_root/$(basename "$source")"
        rm -rf -- "$target"
        cp -R -- "$source" "$target"
    done
    rm -rf -- "$skill_root/network-autofix" "$skill_root/packet-tracer"
    ```

    In PowerShell, perform the same bounded replacement without touching unrelated Skills:

    ```powershell
    python -m tools.skills_governance export --destination .skill-staging-claude --audience operation --client claude
    $skillRoot = Join-Path $HOME ".claude\skills"
    New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
    Get-ChildItem -LiteralPath ".skill-staging-claude\skills" -Directory | ForEach-Object {
        $target = Join-Path $skillRoot $_.Name
        if (Test-Path -LiteralPath $target) { Remove-Item -Recurse -Force -LiteralPath $target }
        Copy-Item -Recurse -LiteralPath $_.FullName -Destination $target
    }
    foreach ($name in @("network-autofix", "packet-tracer")) {
        $target = Join-Path $skillRoot $name
        if (Test-Path -LiteralPath $target) { Remove-Item -Recurse -Force -LiteralPath $target }
    }
    ```

=== "Codex / OpenAI"

    ```bash
    python -m tools.skills_governance export --destination .skill-staging-openai --audience operation --client openai
    skill_root="${CODEX_HOME:-$HOME/.codex}/skills"
    mkdir -p "$skill_root"
    for source in .skill-staging-openai/skills/*; do
        target="$skill_root/$(basename "$source")"
        rm -rf -- "$target"
        cp -R -- "$source" "$target"
    done
    rm -rf -- "$skill_root/network-autofix" "$skill_root/packet-tracer"
    ```

    The OpenAI projection adds each selected Skill's `agents/openai.yaml`; it does not move
    lifecycle, responsibility, or capability truth into that adapter.

=== "Portable"

    ```bash
    python -m tools.skills_governance export --destination .skill-staging-portable --audience operation --client portable
    ```

    Replace matching directories under the target client's Skill root instead of merging their
    contents. Remove `network-autofix` and the legacy `packet-tracer` directory if present, while
    leaving unrelated user Skills untouched. This projection contains no client adapter.

Use `--audience development` for repository-development workflows. `--include-explicit` is reserved
for an intentional explicit-only projection; it never makes a PLANNED or RETIRED Skill eligible.

## Updating

After `git pull`, export to a fresh or removed staging destination and replace each previously
managed directory rather than overlaying it. If changing audiences, remove any unselected IDs from
the canonical `skills/manifest.json` inventory; preserve every unrelated user Skill. Do not edit
staged output or commit it as another canonical Skill tree.
