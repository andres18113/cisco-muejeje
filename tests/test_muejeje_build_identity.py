from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / "src/packet_tracer_mcp/infrastructure/pts/build.py"


def _build_api():
    assert MODULE.exists(), "build foundation module must exist"
    from src.packet_tracer_mcp.infrastructure.pts import build
    return build


def test_recipe_id_is_canonical_and_rejects_nan():
    build = _build_api()
    left = {"source": {"tree": "abc", "commit": "def"}, "inputs": [1, 2]}
    right = {"inputs": [1, 2], "source": {"commit": "def", "tree": "abc"}}
    assert build.recipe_id(left) == build.recipe_id(right)
    assert build.recipe_id(left) == "5a026bbe206cc5170da229ae459962e8c163a4d025606d9fff0c54e8676e8e69"
    with pytest.raises(ValueError):
        build.recipe_id({"invalid": float("nan")})


@pytest.mark.parametrize("field", [
    "source_commit", "source_tree", "manifest", "build_options",
    "builder_version", "builder_hash", "own_inputs", "reference_inputs",
])
def test_recipe_identity_changes_for_every_evidence_dimension(field: str):
    build = _build_api()
    recipe = {
        "source": {"commit": "a", "tree": "b"},
        "manifest": {"sha256": "c"},
        "build_options": {"module_id": "m"},
        "builder": {"version": "1", "sha256": "d"},
        "own_inputs": [{"path": "own", "sha256": "e"}],
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
    build = _build_api()
    artifact = tmp_path / "candidate.pts"
    artifact.write_bytes(b"synthetic bytes, not a real pts")
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()

    assert build.artifact_sha256(artifact) == expected
    with pytest.raises(FileNotFoundError):
        build.artifact_sha256(tmp_path / "missing.pts")
