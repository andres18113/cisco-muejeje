from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import unquote


LIFECYCLES = {"active", "planned", "deprecated", "retired"}
CONSUMERS = {"development", "operation", "both"}
DISTRIBUTION_MODES = {"normal", "explicit_only", "none"}
AUDIENCES = {"development", "operation"}
CLIENTS = {'portable', 'openai', 'claude'}
SOURCE_ANCHOR_ROLES = {"owner", "negative_boundary"}
MANIFEST_ROOT_FIELDS = {"schema_version", "canonical_root", "skills"}
MANIFEST_SKILL_FIELDS = {
    "id",
    "path",
    "lifecycle",
    "consumer",
    "primary_responsibility",
    "source_anchors",
    "supporter_sets",
    "distribution",
}
SOURCE_ANCHOR_FIELDS = {"path", "symbol", "role"}
DISTRIBUTION_FIELDS = {"mode", "audiences"}
PROJECT_FRONTMATTER_FIELDS = {
    "consumer",
    "distribution",
    "lifecycle",
    "owner",
    "primary_responsibility",
    "source_anchors",
    "supporter_sets",
}
ADAPTER_TOP_LEVEL_FIELDS = {"interface", "dependencies", "policy"}
ADAPTER_INTERFACE_FIELDS = {
    "display_name",
    "short_description",
    "icon_small",
    "icon_large",
    "brand_color",
    "default_prompt",
}
ADAPTER_POLICY_FIELDS = {"allow_implicit_invocation"}
ADAPTER_DEPENDENCY_TOOL_FIELDS = {
    "type",
    "value",
    "description",
    "transport",
    "url",
}
ADAPTER_FORBIDDEN_GOVERNANCE_FIELDS = PROJECT_FRONTMATTER_FIELDS | {
    "canonical_id",
    "capability_matrix",
    "capability_status",
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


@dataclass(frozen=True)
class SelectedSkill:
    skill_id: str
    canonical_path: str
    lifecycle: str
    distribution_mode: str
    audiences: tuple[str, ...]


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


def _is_quoted_yaml_string(value: str) -> bool:
    return len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"


def _validate_openai_dependencies(lines: list[tuple[int, str]]) -> tuple[str, ...]:
    errors: list[str] = []
    tools_declared = False
    items: list[dict[str, str]] = []
    current_item: dict[str, str] | None = None

    def add_field(line_number: int, key: str, raw_value: str) -> None:
        nonlocal current_item
        if current_item is None:
            errors.append(f"adapter line {line_number} declares a tool field before a list item")
            return
        if key not in ADAPTER_DEPENDENCY_TOOL_FIELDS:
            errors.append(f"adapter dependency tool has unknown field {key!r}")
        if key in current_item:
            errors.append(f"adapter dependency tool repeats field {key!r}")
            return
        if not _is_quoted_yaml_string(raw_value):
            errors.append(f"adapter dependency tool.{key} must be a quoted string")
        current_item[key] = _yaml_scalar(raw_value)

    for line_number, line in lines:
        indent = len(line) - len(line.lstrip())
        if indent == 2:
            if not re.fullmatch(r"\s{2}tools:\s*", line):
                errors.append(f"adapter line {line_number} must declare dependencies.tools")
                continue
            if tools_declared:
                errors.append("adapter repeats dependencies.tools")
            tools_declared = True
            current_item = None
            continue
        if indent == 4:
            match = re.fullmatch(
                r"\s{4}-\s+([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*",
                line,
            )
            if not match or not tools_declared:
                errors.append(f"adapter line {line_number} must start a dependency tool item")
                current_item = None
                continue
            current_item = {}
            items.append(current_item)
            add_field(line_number, *match.groups())
            continue
        if indent == 6:
            match = re.fullmatch(
                r"\s{6}([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*",
                line,
            )
            if not match:
                errors.append(f"adapter line {line_number} must contain a dependency scalar")
                continue
            add_field(line_number, *match.groups())
            continue
        errors.append(f"adapter line {line_number} has invalid dependency indentation")

    if not tools_declared:
        errors.append("adapter dependencies must declare tools")
    if tools_declared and not items:
        errors.append("adapter dependencies.tools must contain at least one item")
    for index, item in enumerate(items):
        for field in sorted({"type", "value"} - item.keys()):
            errors.append(f"adapter dependency tool {index} is missing {field!r}")
        if item.get("type") not in {None, "mcp"}:
            errors.append("adapter dependency tool type must be 'mcp'")
    return tuple(errors)


def _parse_openai_adapter(
    text: str,
) -> tuple[dict[str, dict[str, str]], tuple[str, ...]]:
    sections: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    current_section: str | None = None
    dependency_lines: list[tuple[int, str]] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        leading = line[: len(line) - len(line.lstrip())]
        if "\t" in leading:
            errors.append(f"adapter line {line_number} uses tab indentation")
            continue
        indent = len(leading)
        key_match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_-]*):", line)
        if key_match and key_match.group(1) in ADAPTER_FORBIDDEN_GOVERNANCE_FIELDS:
            errors.append(
                f"adapter contains forbidden project governance field {key_match.group(1)!r}"
            )

        if indent == 0:
            match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):\s*", line)
            if not match:
                errors.append(f"adapter line {line_number} must declare a mapping section")
                current_section = None
                continue
            current_section = match.group(1)
            if current_section not in ADAPTER_TOP_LEVEL_FIELDS:
                errors.append(f"adapter has unknown top-level field {current_section!r}")
            if current_section in sections:
                errors.append(f"adapter repeats top-level field {current_section!r}")
            sections.setdefault(current_section, {})
            continue

        if current_section is None:
            errors.append(f"adapter line {line_number} is outside a top-level section")
            continue
        if current_section == "dependencies":
            dependency_lines.append((line_number, line))
            continue
        if indent != 2:
            errors.append(
                f"adapter line {line_number} must use two-space section indentation"
            )
            continue
        match = re.fullmatch(r"\s{2}([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*", line)
        if not match:
            errors.append(f"adapter line {line_number} must contain a scalar field")
            continue
        key, raw_value = match.groups()
        allowed_fields = (
            ADAPTER_INTERFACE_FIELDS
            if current_section == "interface"
            else ADAPTER_POLICY_FIELDS
        )
        if key not in allowed_fields:
            errors.append(f"adapter {current_section} has unknown field {key!r}")
        if key in sections[current_section]:
            errors.append(f"adapter repeats {current_section}.{key}")
            continue
        if current_section == "interface" and not _is_quoted_yaml_string(raw_value):
            errors.append(f"adapter interface.{key} must be a quoted string")
        if current_section == "policy" and raw_value not in {"true", "false"}:
            errors.append(f"adapter policy.{key} must be a boolean")
        sections[current_section][key] = _yaml_scalar(raw_value)

    if "dependencies" in sections:
        errors.extend(_validate_openai_dependencies(dependency_lines))
    return sections, tuple(errors)


def validate_openai_adapter(skill_id: str, text: str) -> tuple[str, ...]:
    sections, parse_errors = _parse_openai_adapter(text)
    errors = list(parse_errors)
    interface = sections.get("interface", {})
    policy = sections.get("policy", {})
    display_name = interface.get("display_name")
    short_description = interface.get("short_description")
    default_prompt = interface.get("default_prompt")

    if not display_name:
        errors.append("adapter display_name is required")
    if short_description is None or not 25 <= len(short_description) <= 64:
        errors.append("adapter short_description must contain 25-64 characters")
    if default_prompt is None or f"${skill_id}" not in default_prompt:
        errors.append("adapter default_prompt must invoke its canonical Skill id")
    if skill_id == "network-autofix":
        implicit = policy.get("allow_implicit_invocation")
        if implicit != "false":
            errors.append("network-autofix adapter must disable implicit invocation")
    return tuple(errors)


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


def _validate_object_fields(
    value: dict[str, Any],
    *,
    required: set[str],
    allowed: set[str],
    label: str,
    errors: list[str],
) -> None:
    for field in sorted(required - value.keys()):
        errors.append(f"{label} is missing required field {field!r}")
    for field in sorted(value.keys() - allowed):
        errors.append(f"{label} has unknown field {field!r}")


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
    *,
    manifest_data: dict[str, Any] | None = None,
) -> ValidationReport:
    repo_root = repo_root.resolve()
    errors: list[str] = []
    metrics: list[ContextMetric] = []
    if manifest_path is not None and manifest_data is not None:
        return ValidationReport(
            errors=("manifest_path and manifest_data are mutually exclusive",),
            metrics=(),
        )
    if manifest_data is None:
        try:
            manifest = load_manifest(repo_root, manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return ValidationReport(errors=(str(exc),), metrics=())
    else:
        manifest = manifest_data

    _validate_object_fields(
        manifest,
        required=MANIFEST_ROOT_FIELDS,
        allowed=MANIFEST_ROOT_FIELDS,
        label="manifest",
        errors=errors,
    )

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
        _validate_object_fields(
            raw_entry,
            required=MANIFEST_SKILL_FIELDS,
            allowed=MANIFEST_SKILL_FIELDS,
            label=label,
            errors=errors,
        )
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
            _validate_object_fields(
                distribution,
                required=DISTRIBUTION_FIELDS,
                allowed=DISTRIBUTION_FIELDS,
                label=f"{skill_id}: distribution",
                errors=errors,
            )
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
            if mode == "normal" and lifecycle != "active":
                errors.append(f"{skill_id}: {lifecycle} skill cannot use normal distribution")
            if mode in {"normal", "explicit_only"} and not audiences:
                errors.append(f"{skill_id}: distributable mode requires an audience")
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
                _validate_object_fields(
                    anchor,
                    required={"path", "symbol"},
                    allowed=SOURCE_ANCHOR_FIELDS,
                    label=f"{skill_id}: source anchor {anchor_index}",
                    errors=errors,
                )
                anchor_path = anchor.get("path")
                symbol = anchor.get("symbol")
                role = anchor.get("role", "owner")
                if not isinstance(anchor_path, str) or not anchor_path:
                    errors.append(f"{skill_id}: source anchor {anchor_index} has no path")
                else:
                    resolved = _resolved_within(repo_root, anchor_path)
                    if resolved is None or not resolved.is_file():
                        errors.append(f"{skill_id}: source anchor path does not exist: {anchor_path}")
                if not isinstance(symbol, str) or not symbol.strip():
                    errors.append(f"{skill_id}: source anchor {anchor_index} has no symbol")
                if role not in SOURCE_ANCHOR_ROLES:
                    errors.append(
                        f"{skill_id}: source anchor {anchor_index} has invalid role {role!r}"
                    )
                if skill_id == "network-autofix" and role != "negative_boundary":
                    errors.append(
                        "network-autofix source anchors must be explicit negative boundaries"
                    )

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
            errors.extend(
                f"{skill_id}: {error}"
                for error in validate_openai_adapter(skill_id, adapter_text)
            )

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


def _validated_manifest(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    manifest = load_manifest(repo_root)
    report = validate_skill_governance(repo_root, manifest_data=manifest)
    if not report.ok:
        details = '; '.join(report.errors)
        raise ValueError(f'Skill governance validation failed: {details}')
    return manifest


def select_skills(
    repo_root: Path,
    *,
    audience: str,
    include_explicit: bool = False,
) -> tuple[SelectedSkill, ...]:
    repo_root = repo_root.resolve()
    manifest = _validated_manifest(repo_root)
    if audience not in AUDIENCES:
        raise ValueError(f'Unsupported Skill audience: {audience!r}')

    selected: list[SelectedSkill] = []
    for entry in manifest['skills']:
        lifecycle = entry['lifecycle']
        distribution = entry['distribution']
        mode = distribution['mode']
        audiences = tuple(distribution['audiences'])
        if lifecycle in {'planned', 'retired'} or mode == 'none':
            continue
        if audience not in audiences:
            continue
        if mode == 'normal' and lifecycle != 'active':
            continue
        if mode == 'explicit_only' and not include_explicit:
            continue
        selected.append(
            SelectedSkill(
                skill_id=entry['id'],
                canonical_path=entry['path'],
                lifecycle=lifecycle,
                distribution_mode=mode,
                audiences=audiences,
            )
        )
    return tuple(sorted(selected, key=lambda item: item.skill_id))


def _copy_portable_resources(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    canonical_source = source.resolve(strict=True)
    paths = sorted(source.rglob('*'), key=lambda path: path.relative_to(source).as_posix())
    for path in paths:
        relative = path.relative_to(source)
        if path.is_symlink():
            raise ValueError(f'Skill projection does not support symlinks: {path}')
        try:
            path.resolve(strict=True).relative_to(canonical_source)
        except (FileNotFoundError, ValueError) as exc:
            raise ValueError(f'Skill resource escapes canonical Skill: {path}') from exc
        if relative.parts and relative.parts[0] == 'agents':
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        else:
            raise ValueError(f'Unsupported Skill resource: {path}')


def _projection_source(repo_root: Path, skill: SelectedSkill) -> Path:
    declared_root = repo_root / 'skills'
    declared_skill = repo_root / skill.canonical_path
    declared_source = declared_skill.parent
    for path in (declared_root, declared_source, declared_skill):
        if path.is_symlink():
            raise ValueError(f'Skill projection does not support symlinks: {path}')
    try:
        canonical_root = declared_root.resolve(strict=True)
        source = declared_source.resolve(strict=True)
        skill_file = declared_skill.resolve(strict=True)
        canonical_root.relative_to(repo_root)
        source.relative_to(canonical_root)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(
            f'{skill.skill_id}: canonical projection source escapes skills/'
        ) from exc
    if source.name != skill.skill_id or skill_file.parent != source or not skill_file.is_file():
        raise ValueError(f'{skill.skill_id}: canonical projection identity is inconsistent')
    return source


def _projection_target(staging: Path, skill: SelectedSkill) -> Path:
    target = (staging / Path(skill.canonical_path).parent).resolve()
    try:
        target.relative_to(staging)
    except ValueError as exc:
        raise ValueError(f'{skill.skill_id}: projection target escapes staging') from exc
    return target


def export_projection(
    repo_root: Path,
    destination: Path,
    *,
    audience: str,
    client: str,
    include_explicit: bool = False,
) -> tuple[SelectedSkill, ...]:
    repo_root = repo_root.resolve()
    selected = select_skills(
        repo_root,
        audience=audience,
        include_explicit=include_explicit,
    )
    if client not in CLIENTS:
        raise ValueError(f'Unsupported Skill projection client: {client!r}')

    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f'Skill projection destination already exists: {destination}')
    parent = destination.parent
    if not parent.is_dir():
        raise FileNotFoundError(f'Skill projection parent does not exist: {parent}')
    canonical_root = (repo_root / 'skills').resolve()
    try:
        destination.relative_to(canonical_root)
    except ValueError:
        pass
    else:
        raise ValueError('Skill projections cannot be written inside the canonical skills root')

    staging = Path(
        tempfile.mkdtemp(prefix=f'.{destination.name}.tmp-', dir=parent)
    ).resolve()
    try:
        (staging / 'skills').mkdir()
        for skill in selected:
            source = _projection_source(repo_root, skill)
            target = _projection_target(staging, skill)
            _copy_portable_resources(source, target)
            if client == 'openai':
                adapter_source = source / 'agents' / 'openai.yaml'
                if adapter_source.is_symlink() or not adapter_source.is_file():
                    raise ValueError(
                        f'{skill.skill_id}: OpenAI adapter must be a regular canonical file'
                    )
                try:
                    adapter_source.resolve(strict=True).relative_to(source)
                except (FileNotFoundError, ValueError) as exc:
                    raise ValueError(
                        f'{skill.skill_id}: OpenAI adapter escapes its canonical Skill'
                    ) from exc
                adapter_target = target / 'agents' / 'openai.yaml'
                adapter_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(adapter_source, adapter_target)
        if destination.exists():
            raise FileExistsError(
                f'Skill projection destination appeared during export: {destination}'
            )
        staging.rename(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return selected


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


def _print_validation_status(report: ValidationReport) -> None:
    if report.errors:
        print('SKILL_GOVERNANCE=FAIL')
        for error in report.errors:
            print(f'ERROR {error}')
    else:
        print('SKILL_GOVERNANCE=PASS')


def _print_metrics(report: ValidationReport) -> None:
    print('CONTEXT_METRICS')
    for metric in report.metrics:
        print(
            metric.skill_id,
            f'description_chars={metric.description_characters}',
            f'description_tokens~={metric.description_estimated_tokens}',
            f'body_chars={metric.body_characters}',
            f'body_tokens~={metric.body_estimated_tokens}',
            f'references_chars={metric.deferred_reference_characters}',
            f'references_tokens~={metric.deferred_reference_estimated_tokens}',
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate governed repository Skills.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing skills/.",
    )
    subparsers = parser.add_subparsers(dest='command')
    subparsers.add_parser('validate', help='Validate canonical Skill governance.')
    subparsers.add_parser('metrics', help='Report static Skill context metrics.')
    export_parser = subparsers.add_parser(
        'export',
        help='Export a deterministic client projection.',
    )
    export_parser.add_argument('--destination', type=Path, required=True)
    export_parser.add_argument('--audience', choices=sorted(AUDIENCES), required=True)
    export_parser.add_argument('--client', choices=sorted(CLIENTS), required=True)
    export_parser.add_argument(
        '--include-explicit',
        action='store_true',
        help='Include eligible explicit-only Skills.',
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == 'export':
        try:
            selected = export_projection(
                args.repo_root,
                args.destination,
                audience=args.audience,
                client=args.client,
                include_explicit=args.include_explicit,
            )
        except (OSError, ValueError) as exc:
            print('SKILL_EXPORT=FAIL')
            print(f'ERROR {exc}')
            return 1
        print('SKILL_EXPORT=PASS')
        print(f'destination={args.destination.resolve()}')
        print(f'audience={args.audience}')
        print(f'client={args.client}')
        print(f'skills={len(selected)}')
        return 0

    report = validate_skill_governance(args.repo_root)
    if args.command == 'metrics':
        if report.errors:
            print('SKILL_GOVERNANCE=FAIL')
            for error in report.errors:
                print(f'ERROR {error}')
        _print_metrics(report)
        return 0 if report.ok else 1
    if args.command == 'validate':
        _print_validation_status(report)
    else:
        _print_validation_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
