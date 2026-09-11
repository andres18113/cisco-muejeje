"""Source, hash and recipe identity.

`build_recipe_id` answers "which inputs produced this", and it must change when
any evidence dimension changes. The artifact hash answers "which bytes exist",
is measured externally, and is never embedded in the artifact it describes
(MJ-017).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.muejeje.support import build_api, git, make_repo


def test_recipe_id_is_canonical_and_rejects_nan():
    build = build_api()
    left = {"source": {"tree": "abc", "commit": "def"}, "inputs": [1, 2]}
    right = {"inputs": [1, 2], "source": {"commit": "def", "tree": "abc"}}
    assert build.recipe_id(left) == build.recipe_id(right)
    assert build.recipe_id(left) == "5a026bbe206cc5170da229ae459962e8c163a4d025606d9fff0c54e8676e8e69"
    with pytest.raises(ValueError):
        build.recipe_id({"invalid": float("nan")})


@pytest.mark.parametrize("field", [
    "source_commit", "source_tree", "manifest", "build_options",
    "builder_version", "builder_hash", "artifact_inputs", "tooling_inputs",
    "reference_inputs",
])
def test_recipe_identity_changes_for_every_evidence_dimension(field: str):
    build = build_api()
    recipe = {
        "source": {"commit": "a", "tree": "b"},
        "manifest": {"sha256": "c"},
        "build_options": {"module_id": "m"},
        "builder": {"version": "1", "sha256": "d"},
        "artifact_inputs": [{"path": "artifact", "sha256": "e"}],
        "tooling_inputs": [{"path": "tooling", "sha256": "f"}],
        "reference_inputs": [{"path": "ref", "sha256": "f"}],
    }
    changed = json.loads(json.dumps(recipe))
    if field == "source_commit":
        changed["source"]["commit"] = "changed"
    elif field == "source_tree":
        changed["source"]["tree"] = "changed"
    elif field == "manifest":
        changed[field]["sha256"] = "changed"
    elif field == "build_options":
        changed[field]["module_id"] = "changed"
    elif field == "builder_version":
        changed["builder"]["version"] = "changed"
    elif field == "builder_hash":
        changed["builder"]["sha256"] = "changed"
    else:
        changed[field][0]["sha256"] = "changed"
    assert build.recipe_id(recipe) != build.recipe_id(changed)


def test_artifact_hash_is_external_byte_measurement(tmp_path: Path):
    build = build_api()
    artifact = tmp_path / "candidate.pts"
    artifact.write_bytes(b"synthetic bytes, not a real pts")
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()

    assert build.artifact_sha256(artifact) == expected
    with pytest.raises(FileNotFoundError):
        build.artifact_sha256(tmp_path / "missing.pts")


def test_tooling_inputs_participate_in_recipe_identity(tmp_path: Path):
    """Changing the auditor changes the recipe, even though it ships nothing."""
    root, manifest_path = make_repo(tmp_path)
    build = build_api()
    before = build.inspect_build(root, manifest_path)["recipe"]

    tooling = root / "tools/build_muejeje_pts.py"
    tooling.write_text(
        "own:tools/build_muejeje_pts.py\n# audited differently\n", encoding="utf-8",
    )
    git(root, "add", "tools/build_muejeje_pts.py")
    git(root, "commit", "-qm", "tooling changed")
    after = build.inspect_build(root, manifest_path)["recipe"]

    assert before["tooling_inputs"] != after["tooling_inputs"]
    assert before["artifact_inputs"] == after["artifact_inputs"]
    assert build.recipe_id(before) != build.recipe_id(after)


def test_every_auditor_module_participates_in_recipe_identity(tmp_path: Path):
    """Splitting the auditor must not let a change escape recipe identity.

    Before the split, one `build.py` carried every rule, so any change to the
    auditor moved the recipe id. Cohesive modules only keep that property if
    each one is declared.
    """
    from src.packet_tracer_mcp.infrastructure.pts import inventory

    root, manifest_path = make_repo(tmp_path)
    build = build_api()
    baseline = build.recipe_id(build.inspect_build(root, manifest_path)["recipe"])
    for logical in inventory.EXPECTED_TOOLING_INPUTS:
        path = root / logical
        path.write_text(f"own:{logical}\n# perturbed\n", encoding="utf-8")
        git(root, "add", logical)
        git(root, "commit", "-qm", f"perturb {logical}")
        moved = build.recipe_id(build.inspect_build(root, manifest_path)["recipe"])
        assert moved != baseline, f"{logical} is outside recipe identity"
        baseline = moved


def test_source_identity_reports_commit_tree_and_cleanliness(tmp_path: Path):
    from src.packet_tracer_mcp.infrastructure.pts import provenance

    root, _ = make_repo(tmp_path)
    identity = provenance.inspect_source(root.resolve())
    assert len(identity.commit) == 40 and len(identity.tree) == 40
    assert identity.clean is True
    assert "muejeje_pts/script-engine/220_lifecycle.js" in identity.tracked

    (root / "muejeje_pts/script-engine/220_lifecycle.js").write_text("x", encoding="utf-8")
    assert provenance.inspect_source(root.resolve()).clean is False


def test_source_identity_refuses_a_directory_that_is_not_the_top_level(tmp_path: Path):
    from src.packet_tracer_mcp.infrastructure.pts import provenance

    root, _ = make_repo(tmp_path)
    with pytest.raises(ValueError, match="top-level"):
        provenance.inspect_source((root / "muejeje_pts").resolve())
