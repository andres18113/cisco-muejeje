from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.skills_governance import (
    find_raw_bypass_recipes,
    load_manifest,
    parse_skill_text,
    validate_openai_adapter,
    validate_skill_governance,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _validate_modified_manifest(tmp_path: Path, mutate) -> tuple[str, ...]:
    manifest = copy.deepcopy(load_manifest(REPO_ROOT))
    mutate(manifest)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return validate_skill_governance(REPO_ROOT, manifest_path).errors


def test_canonical_skill_governance_is_valid() -> None:
    report = validate_skill_governance(REPO_ROOT)

    assert report.errors == ()
    assert len(report.metrics) == 17
    assert all(metric.description_characters > 0 for metric in report.metrics)
    assert all(metric.body_characters > 0 for metric in report.metrics)


def test_voice_registration_failure_stays_with_voice_owner() -> None:
    routing_cases = json.loads(
        (REPO_ROOT / "skills" / "routing-evals.json").read_text(encoding="utf-8")
    )["cases"]
    regression = next(
        case
        for case in routing_cases
        if case["intent"].startswith("A phone that should follow the approved voice plan")
    )
    voice = parse_skill_text(
        (REPO_ROOT / "skills" / "enterprise-voice" / "SKILL.md").read_text(
            encoding="utf-8"
        )
    )
    diagnosis = parse_skill_text(
        (REPO_ROOT / "skills" / "network-diagnosis" / "SKILL.md").read_text(
            encoding="utf-8"
        )
    )

    assert regression["expected_primary"] == "enterprise-voice"
    assert "network-diagnosis" in regression["excluded_primaries"]
    assert "failed phone registration" in voice.description.lower()
    assert "enterprise-voice" in diagnosis.description


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda manifest: manifest["skills"][0].update(lifecycle="unknown"),
            "invalid lifecycle",
        ),
        (
            lambda manifest: manifest["skills"][11]["distribution"].update(
                mode="normal", audiences=["operation"]
            ),
            "network-autofix cannot enter normal distribution",
        ),
        (
            lambda manifest: manifest["skills"][0].update(
                supporter_sets=[["enterprise-configuration", "packet-tracer-runtime", "routing-igp"]]
            ),
            "exceeds two supporters",
        ),
        (
            lambda manifest: manifest["skills"][0].update(
                supporter_sets=[["missing-skill"]]
            ),
            "unknown supporting skill",
        ),
        (
            lambda manifest: manifest["skills"][0]["source_anchors"][0].update(
                path="src/packet_tracer_mcp/does_not_exist.py"
            ),
            "source anchor path does not exist",
        ),
        (
            lambda manifest: manifest["skills"][0]["source_anchors"][0].update(
                role="invented"
            ),
            "invalid role",
        ),
        (
            lambda manifest: manifest["skills"][11]["source_anchors"][0].pop("role"),
            "network-autofix source anchors must be explicit negative boundaries",
        ),
        (
            lambda manifest: manifest["skills"][0].update(eligible=True),
            "unknown field 'eligible'",
        ),
        (
            lambda manifest: manifest["skills"][0]["distribution"].update(eligible=True),
            "distribution has unknown field 'eligible'",
        ),
        (
            lambda manifest: manifest["skills"][0]["source_anchors"][0].update(
                line=42
            ),
            "source anchor 0 has unknown field 'line'",
        ),
        (
            lambda manifest: manifest.update(capability_matrix={}),
            "manifest has unknown field 'capability_matrix'",
        ),
        (
            lambda manifest: manifest["skills"][0].update(lifecycle="deprecated"),
            "deprecated skill cannot use normal distribution",
        ),
        (
            lambda manifest: manifest["skills"][0]["distribution"].update(
                mode="explicit_only", audiences=[]
            ),
            "distributable mode requires an audience",
        ),
    ],
)
def test_manifest_invariant_failures_are_reported(
    tmp_path: Path,
    mutate,
    expected: str,
) -> None:
    errors = _validate_modified_manifest(tmp_path, mutate)

    assert any(expected in error for error in errors)


def test_support_cycles_are_rejected(tmp_path: Path) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        skills = manifest["skills"]
        skills[1]["supporter_sets"] = [["campus-layer2"]]

    errors = _validate_modified_manifest(tmp_path, mutate)

    assert any("support graph contains a cycle" in error for error in errors)


def test_project_governance_fields_are_visible_to_portability_validation() -> None:
    document = parse_skill_text(
        """---
name: example-skill
description: Route a focused example responsibility.
lifecycle: active
---

# Example
"""
    )

    assert "lifecycle" in document.top_level_fields


def test_raw_bypass_recipe_detection_allows_prohibitions() -> None:
    assert find_raw_bypass_recipes("Do not use pt_send_raw as a fallback.") == ()
    assert find_raw_bypass_recipes(
        "Never enable developer-capability-investigation for normal operation."
    ) == ()


def test_raw_bypass_recipe_detection_rejects_operational_instructions() -> None:
    findings = find_raw_bypass_recipes("Use pt_send_raw to execute the command.")
    fenced_findings = find_raw_bypass_recipes("```text\npt_send_raw(payload)\n```")

    assert findings
    assert fenced_findings


def test_openai_adapter_uses_friendly_display_name_and_canonical_prompt_id() -> None:
    errors = validate_openai_adapter(
        "example-skill",
        '''interface:
  display_name: "Friendly Example"
  short_description: "Handle one focused example responsibility"
  default_prompt: "Use $example-skill for this request."
''',
    )

    assert errors == ()


def test_planned_autofix_adapter_requires_explicit_invocation() -> None:
    errors = validate_openai_adapter(
        "network-autofix",
        '''interface:
  display_name: "Network Autofix"
  short_description: "Inspect the future governed remediation boundary"
  default_prompt: "Use $network-autofix only for governance review."
''',
    )

    assert "network-autofix adapter must disable implicit invocation" in errors


def test_openai_adapter_rejects_misnested_interface_fields() -> None:
    errors = validate_openai_adapter(
        "example-skill",
        '''display_name: "Misnested"
interface:
  short_description: "Handle one focused example responsibility"
  default_prompt: "Use $example-skill for this request."
''',
    )

    assert any("mapping section" in error for error in errors)
    assert "adapter display_name is required" in errors


def test_openai_adapter_rejects_project_governance_fields() -> None:
    errors = validate_openai_adapter(
        "example-skill",
        '''interface:
  display_name: "Friendly Example"
  short_description: "Handle one focused example responsibility"
  default_prompt: "Use $example-skill for this request."
lifecycle: active
''',
    )

    assert any("forbidden project governance field 'lifecycle'" in error for error in errors)


def test_openai_adapter_accepts_documented_mcp_dependency_shape() -> None:
    errors = validate_openai_adapter(
        "example-skill",
        '''interface:
  display_name: "Friendly Example"
  short_description: "Handle one focused example responsibility"
  default_prompt: "Use $example-skill for this request."
dependencies:
  tools:
    - type: "mcp"
      value: "packet-tracer"
      description: "Packet Tracer MCP server"
      transport: "stdio"
policy:
  allow_implicit_invocation: true
''',
    )

    assert errors == ()


def test_openai_adapter_rejects_malformed_dependencies_and_policy() -> None:
    errors = validate_openai_adapter(
        "example-skill",
        '''interface:
  display_name: "Friendly Example"
  short_description: "Handle one focused example responsibility"
  default_prompt: "Use $example-skill for this request."
dependencies:
  tools:
    - type "mcp"
policy:
  allow_implicit_invocation: banana
''',
    )

    assert any("dependency tool item" in error for error in errors)
    assert "adapter policy.allow_implicit_invocation must be a boolean" in errors
