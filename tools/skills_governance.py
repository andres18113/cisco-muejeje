from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import unquote


LIFECYCLES = {"active", "planned", "deprecated", "retired"}
CONSUMERS = {"development", "operation", "both"}
DISTRIBUTION_MODES = {"normal", "explicit_only", "none"}
AUDIENCES = {"development", "operation"}
PROJECT_FRONTMATTER_FIELDS = {
    "consumer",
    "distribution",
    "lifecycle",
    "owner",
    "primary_responsibility",
    "source_anchors",
    "supporter_sets",
}
PORTABLE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
ACTION_RECIPE = re.compile(
    r"\b(?:call|enable|execute|fall back to|invoke|run|send|set|use)\b",
    re.IGNORECASE,
)
NEGATION = re.compile(
    r"\b(?:avoid|cannot|can't|do not|don't|must not|never|no operational|not use|without)\b",
    re.IGNORECASE,
)
RAW_MARKERS = (
    "developer-capability-investigation",
    "executeCode(",
    "ipc.network(",
    "pt_send_raw",
    "script-engine js",
    "script engine js",
)


@dataclass(frozen=True)
class SkillDocument:
    name: str
    description: str
    body: str
    top_level_fields: frozenset[str]


@dataclass(frozen=True)
class ContextMetric:
    skill_id: str
    description_characters: int
    description_estimated_tokens: int
    body_characters: int
    body_estimated_tokens: int
    deferred_reference_characters: int
    deferred_reference_estimated_tokens: int


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[str, ...]
    metrics: tuple[ContextMetric, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def _estimated_tokens(characters: int) -> int:
    return (characters + 3) // 4


def _yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
        return parsed if isinstance(parsed, str) else str(parsed)
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def parse_skill_text(text: str, source: str = "<memory>") -> SkillDocument:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{source}: missing opening frontmatter delimiter")

    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing is None:
        raise ValueError(f"{source}: missing closing frontmatter delimiter")

    frontmatter_lines = lines[1:closing]
    top_level_fields: set[str] = set()
    values: dict[str, str] = {}
    index = 0
    while index < len(frontmatter_lines):
        line = frontmatter_lines[index]
        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if not match:
            index += 1
            continue
        key = match.group(1)
        value = (match.group(2) or "").strip()
        if key in top_level_fields:
            raise ValueError(f"{source}: duplicate top-level frontmatter field {key!r}")
        top_level_fields.add(key)
        if value in {">", ">-", "|", "|-"}:
            block_lines: list[str] = []
            index += 1
            while index < len(frontmatter_lines):
                block_line = frontmatter_lines[index]
                if block_line and not block_line[0].isspace():
                    break
                block_lines.append(block_line.strip())
                index += 1
            separator = " " if value.startswith(">") else "\n"
            values[key] = separator.join(part for part in block_lines if part).strip()
            continue
        values[key] = _yaml_scalar(value)
        index += 1

    name = values.get("name", "").strip()
    description = values.get("description", "").strip()
    body = "\n".join(lines[closing + 1 :]).strip()
    return SkillDocument(
        name=name,
        description=description,
        body=body,
        top_level_fields=frozenset(top_level_fields),
    )


def _parse_adapter_scalar(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^\s+{re.escape(key)}:\s*(.+?)\s*$", text)
    return _yaml_scalar(match.group(1)) if match else None


def _reference_targets(document: SkillDocument) -> Iterable[str]:
    for match in MARKDOWN_LINK.finditer(document.body):
        raw_target = match.group(1).strip()
        if raw_target.startswith("<") and ">" in raw_target:
            raw_target = raw_target[1 : raw_target.index(">")]
        else:
            raw_target = raw_target.split(maxsplit=1)[0]
        target = unquote(raw_target.split("#", maxsplit=1)[0])
        if target:
            yield target


def find_raw_bypass_recipes(text: str) -> tuple[str, ...]:
    findings: list[str] = []
    in_fence = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        lowered = line.lower()
        marker = next((item for item in RAW_MARKERS if item.lower() in lowered), None)
        if marker is None:
            continue
        direct_assignment = "pt_mcp_public_surface=developer-capability-investigation" in lowered
        direct_call = "pt_send_raw(" in lowered or "executecode(" in lowered
        if in_fence or direct_assignment or direct_call:
            findings.append(f"line {line_number}: {stripped}")
            continue
        if ACTION_RECIPE.search(line) and not NEGATION.search(line):
            findings.append(f"line {line_number}: {stripped}")
    return tuple(findings)


def load_manifest(
    repo_root: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    path = manifest_path or repo_root / "skills" / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: manifest root must be an object")
    return data


def _resolved_within(root: Path, relative_path: str) -> Path | None:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _find_support_cycle(graph: dict[str, set[str]]) -> tuple[str, ...] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    trail: list[str] = []

    def visit(node: str) -> tuple[str, ...] | None:
        if node in visiting:
            start = trail.index(node)
            return tuple(trail[start:] + [node])
        if node in visited:
            return None
        visiting.add(node)
        trail.append(node)
        for supporter in sorted(graph.get(node, set())):
            cycle = visit(supporter)
            if cycle is not None:
                return cycle
        trail.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in sorted(graph):
        cycle = visit(node)
        if cycle is not None:
            return cycle
    return None


def validate_skill_governance(
    repo_root: Path,
    manifest_path: Path | None = None,
) -> ValidationReport:
    repo_root = repo_root.resolve()
    errors: list[str] = []
    metrics: list[ContextMetric] = []
    try:
        manifest = load_manifest(repo_root, manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return ValidationReport(errors=(str(exc),), metrics=())

    if manifest.get("schema_version") != 1:
        errors.append("manifest schema_version must be 1")
    if manifest.get("canonical_root") != "skills":
        errors.append("manifest canonical_root must be 'skills'")
    entries = manifest.get("skills")
    if not isinstance(entries, list):
        return ValidationReport(
            errors=tuple(errors + ["manifest skills must be a list"]),
            metrics=(),
        )

    skills_root = repo_root / "skills"
    directory_ids = {
        path.name
        for path in skills_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    entry_ids: list[str] = []
    primary_responsibilities: list[str] = []
    support_graph: dict[str, set[str]] = {}
    entries_by_id: dict[str, dict[str, Any]] = {}

    for index, raw_entry in enumerate(entries):
        label = f"manifest skills[{index}]"
        if not isinstance(raw_entry, dict):
            errors.append(f"{label} must be an object")
            continue
        skill_id = raw_entry.get("id")
        if not isinstance(skill_id, str) or not skill_id:
            errors.append(f"{label}.id must be a non-empty string")
            continue
        entry_ids.append(skill_id)
        if skill_id in entries_by_id:
            errors.append(f"duplicate canonical skill id: {skill_id}")
        entries_by_id[skill_id] = raw_entry

        canonical_path = f"skills/{skill_id}/SKILL.md"
        if raw_entry.get("path") != canonical_path:
            errors.append(f"{skill_id}: path must be {canonical_path!r}")
        lifecycle = raw_entry.get("lifecycle")
        consumer = raw_entry.get("consumer")
        if lifecycle not in LIFECYCLES:
            errors.append(f"{skill_id}: invalid lifecycle {lifecycle!r}")
        if consumer not in CONSUMERS:
            errors.append(f"{skill_id}: invalid consumer {consumer!r}")

        responsibility = raw_entry.get("primary_responsibility")
        if not isinstance(responsibility, str) or not responsibility.strip():
            errors.append(f"{skill_id}: primary_responsibility must be non-empty")
        else:
            primary_responsibilities.append(responsibility)

        distribution = raw_entry.get("distribution")
        if not isinstance(distribution, dict):
            errors.append(f"{skill_id}: distribution must be an object")
        else:
            mode = distribution.get("mode")
            audiences = distribution.get("audiences")
            if mode not in DISTRIBUTION_MODES:
                errors.append(f"{skill_id}: invalid distribution mode {mode!r}")
            if not isinstance(audiences, list) or any(
                audience not in AUDIENCES for audience in audiences
            ):
                errors.append(f"{skill_id}: invalid distribution audiences")
                audiences = []
            if len(set(audiences)) != len(audiences):
                errors.append(f"{skill_id}: duplicate distribution audience")
            allowed_audiences = (
                AUDIENCES if consumer == "both" else {consumer} if consumer in AUDIENCES else set()
            )
            if any(audience not in allowed_audiences for audience in audiences):
                errors.append(f"{skill_id}: distribution audience exceeds consumer")
            if lifecycle in {"planned", "retired"} and mode == "normal":
                errors.append(f"{skill_id}: {lifecycle} skill cannot use normal distribution")
            if mode == "normal" and not audiences:
                errors.append(f"{skill_id}: normal distribution requires an audience")
            if mode == "none" and audiences:
                errors.append(f"{skill_id}: distribution mode none requires no audiences")
            if skill_id == "network-autofix" and mode != "none":
                errors.append("network-autofix cannot enter normal distribution")

        anchors = raw_entry.get("source_anchors")
        if not isinstance(anchors, list) or not anchors:
            errors.append(f"{skill_id}: source_anchors must be a non-empty list")
        else:
            for anchor_index, anchor in enumerate(anchors):
                if not isinstance(anchor, dict):
                    errors.append(f"{skill_id}: source anchor {anchor_index} must be an object")
                    continue
                anchor_path = anchor.get("path")
                symbol = anchor.get("symbol")
                if not isinstance(anchor_path, str) or not anchor_path:
                    errors.append(f"{skill_id}: source anchor {anchor_index} has no path")
                else:
                    resolved = _resolved_within(repo_root, anchor_path)
                    if resolved is None or not resolved.is_file():
                        errors.append(f"{skill_id}: source anchor path does not exist: {anchor_path}")
                if not isinstance(symbol, str) or not symbol.strip():
                    errors.append(f"{skill_id}: source anchor {anchor_index} has no symbol")

        supporter_sets = raw_entry.get("supporter_sets")
        support_graph.setdefault(skill_id, set())
        if not isinstance(supporter_sets, list):
            errors.append(f"{skill_id}: supporter_sets must be a list")
        else:
            normalized_sets: set[tuple[str, ...]] = set()
            for set_index, supporter_set in enumerate(supporter_sets):
                if not isinstance(supporter_set, list) or any(
                    not isinstance(item, str) for item in supporter_set
                ):
                    errors.append(f"{skill_id}: supporter set {set_index} must be a string list")
                    continue
                if len(supporter_set) > 2:
                    errors.append(f"{skill_id}: supporter set {set_index} exceeds two supporters")
                if len(set(supporter_set)) != len(supporter_set):
                    errors.append(f"{skill_id}: supporter set {set_index} contains duplicates")
                normalized = tuple(sorted(supporter_set))
                if normalized in normalized_sets:
                    errors.append(f"{skill_id}: duplicate supporter set {set_index}")
                normalized_sets.add(normalized)
                support_graph[skill_id].update(supporter_set)

    if len(entry_ids) != len(set(entry_ids)):
        errors.append("canonical skill identities must be unique")
    if len(primary_responsibilities) != len(set(primary_responsibilities)):
        errors.append("primary responsibilities must be unique")
    if set(entry_ids) != directory_ids:
        missing = sorted(directory_ids - set(entry_ids))
        extra = sorted(set(entry_ids) - directory_ids)
        errors.append(f"manifest inventory mismatch: missing={missing}, extra={extra}")
    if any(str(entry.get("path", "")).replace("\\", "/").startswith("skill/") for entry in entries if isinstance(entry, dict)):
        errors.append("skill/SKILL.md cannot be a canonical manifest entry")

    known_ids = set(entry_ids)
    for primary, supporters in support_graph.items():
        for supporter in sorted(supporters):
            if supporter not in known_ids:
                errors.append(f"{primary}: unknown supporting skill {supporter}")
            if supporter == primary:
                errors.append(f"{primary}: cannot support itself")
    cycle = _find_support_cycle(
        {
            primary: {supporter for supporter in supporters if supporter in known_ids}
            for primary, supporters in support_graph.items()
        }
    )
    if cycle is not None:
        errors.append(f"support graph contains a cycle: {' -> '.join(cycle)}")

    for skill_id in sorted(directory_ids):
        entry = entries_by_id.get(skill_id)
        skill_path = skills_root / skill_id / "SKILL.md"
        try:
            document = parse_skill_text(
                skill_path.read_text(encoding="utf-8"),
                source=skill_path.as_posix(),
            )
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(str(exc))
            continue
        if document.name != skill_id:
            errors.append(f"{skill_id}: portable name {document.name!r} does not match canonical id")
        if not PORTABLE_NAME.fullmatch(document.name) or len(document.name) > 64:
            errors.append(f"{skill_id}: portable name is invalid")
        if not document.description or len(document.description) > 1024:
            errors.append(f"{skill_id}: description must contain 1-1024 characters")
        invented_fields = sorted(document.top_level_fields & PROJECT_FRONTMATTER_FIELDS)
        if invented_fields:
            errors.append(f"{skill_id}: project governance leaked into frontmatter: {invented_fields}")

        for target in _reference_targets(document):
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("#"):
                continue
            resolved = _resolved_within(skill_path.parent, target)
            if resolved is None or not resolved.exists():
                errors.append(f"{skill_id}: unresolved relative reference {target!r}")

        adapter_path = skill_path.parent / "agents" / "openai.yaml"
        if not adapter_path.is_file():
            errors.append(f"{skill_id}: missing agents/openai.yaml")
        else:
            adapter_text = adapter_path.read_text(encoding="utf-8")
            display_name = _parse_adapter_scalar(adapter_text, "display_name")
            short_description = _parse_adapter_scalar(adapter_text, "short_description")
            default_prompt = _parse_adapter_scalar(adapter_text, "default_prompt")
            if display_name != skill_id:
                errors.append(f"{skill_id}: adapter display_name must match canonical id")
            if short_description is None or not 25 <= len(short_description) <= 64:
                errors.append(f"{skill_id}: adapter short_description must contain 25-64 characters")
            if default_prompt is None or skill_id not in default_prompt:
                errors.append(f"{skill_id}: adapter default_prompt must reference its canonical id")

        scanned_paths = [skill_path]
        references_dir = skill_path.parent / "references"
        if references_dir.is_dir():
            scanned_paths.extend(sorted(references_dir.rglob("*.md")))
        deferred_chars = 0
        for scanned_path in scanned_paths:
            scanned_text = scanned_path.read_text(encoding="utf-8")
            if scanned_path != skill_path:
                deferred_chars += len(scanned_text)
            for finding in find_raw_bypass_recipes(scanned_text):
                errors.append(
                    f"{skill_id}: operational raw-bypass recipe in "
                    f"{scanned_path.relative_to(repo_root).as_posix()} {finding}"
                )

        metrics.append(
            ContextMetric(
                skill_id=skill_id,
                description_characters=len(document.description),
                description_estimated_tokens=_estimated_tokens(len(document.description)),
                body_characters=len(document.body),
                body_estimated_tokens=_estimated_tokens(len(document.body)),
                deferred_reference_characters=deferred_chars,
                deferred_reference_estimated_tokens=_estimated_tokens(deferred_chars),
            )
        )

        if entry is None:
            continue

    return ValidationReport(errors=tuple(sorted(set(errors))), metrics=tuple(metrics))


def _print_validation_report(report: ValidationReport) -> None:
    if report.errors:
        print("SKILL_GOVERNANCE=FAIL")
        for error in report.errors:
            print(f"ERROR {error}")
    else:
        print("SKILL_GOVERNANCE=PASS")
    print("CONTEXT_METRICS")
    for metric in report.metrics:
        print(
            metric.skill_id,
            f"description_chars={metric.description_characters}",
            f"description_tokens~={metric.description_estimated_tokens}",
            f"body_chars={metric.body_characters}",
            f"body_tokens~={metric.body_estimated_tokens}",
            f"references_chars={metric.deferred_reference_characters}",
            f"references_tokens~={metric.deferred_reference_estimated_tokens}",
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate governed repository Skills.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing skills/.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_skill_governance(args.repo_root)
    _print_validation_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
