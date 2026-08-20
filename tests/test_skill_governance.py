from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.skills_governance import (
    find_raw_bypass_recipes,
    load_manifest,
    parse_skill_text,
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
