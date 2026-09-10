"""Shared fixtures and measurement helpers for the Muejeje test area.

Small on purpose. This module holds the synthetic repository the build audit
runs against and the file-measurement helpers the architecture gates use; it
holds no assertions of its own, so a behaviour claim always lives in the test
module whose responsibility it is (MJ-020).
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_MODULE = REPO_ROOT / "src/packet_tracer_mcp/infrastructure/pts/build.py"
PTS_PACKAGE = REPO_ROOT / "src/packet_tracer_mcp/infrastructure/pts"
CLI = REPO_ROOT / "tools/build_muejeje_pts.py"
SOURCE_ROOT = REPO_ROOT / "muejeje_pts"
SCRIPT_ENGINE = SOURCE_ROOT / "script-engine"
REPO_MANIFEST = SOURCE_ROOT / "manifest/muejeje-build-manifest.json"
MUEJEJE_TESTS = Path(__file__).resolve().parent
REFERENCE_PATH = "local-references/api-reference.txt"

INSTALLED_BUILDER = Path(
    "C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe"
)

TOOLING_INPUTS = [
    "src/packet_tracer_mcp/infrastructure/pts/__init__.py",
    "src/packet_tracer_mcp/infrastructure/pts/build.py",
    "src/packet_tracer_mcp/infrastructure/pts/build_state.py",
    "src/packet_tracer_mcp/infrastructure/pts/inventory.py",
    "src/packet_tracer_mcp/infrastructure/pts/manifest.py",
    "src/packet_tracer_mcp/infrastructure/pts/provenance.py",
    "tools/build_muejeje_pts.py",
]

RESOLVED_OPTIONS = {
    "engine_script_order": ["muejeje_pts/script-engine/lifecycle.js"],
    "custom_interface_order": ["muejeje_pts/interface/index.html"],
    "module_id": "com.muejeje.runtime",
    "startup": "on_startup",
    "privileges": ["PrivGetNetwork"],
}


def build_api():
    from src.packet_tracer_mcp.infrastructure.pts import build
    return build


def repo_manifest() -> dict[str, Any]:
    """The real manifest this repository ships."""
    return json.loads(REPO_MANIFEST.read_text(encoding="utf-8"))


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True,
    )


def manifest_document() -> dict[str, Any]:
    """The manifest the synthetic repository declares.

    It mirrors the real schema-2 document but names synthetic file contents, so
    a test can perturb one field without touching the repository.
    """
    return {
        "schema_version": 2,
        "extension": {"name": "muejeje", "version": "0.1.0"},
        "output": {"artifact": "muejeje.pts", "report": "muejeje.build.json"},
        "artifact_inputs": list(repo_manifest()["artifact_inputs"]),
        "tooling_inputs": list(TOOLING_INPUTS),
        "reference_inputs": [],
        "builder": {
            "name": "Cisco Packet Tracer", "version": "9.0.1.0858",
            "kind": "packet-tracer-scripting-interface",
            "sha256": "843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1",
        },
        "build_options": {
            "engine_script_order": None, "custom_interface_order": None,
            "module_id": None, "startup": None, "privileges": None,
        },
        "packaging": {
            "status": "unresolved", "compiler_command": None,
            "content_validation": None,
        },
    }


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A committed synthetic checkout whose declared inputs all exist."""
    root = tmp_path / "source"
    document = manifest_document()
    manifest_path = root / "muejeje_pts/manifest/muejeje-build-manifest.json"
    declared = document["artifact_inputs"] + document["tooling_inputs"]
    for logical in declared:
        path = root / logical
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"own:{logical}\n", encoding="utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    (root / ".gitignore").write_text("dist/\nlocal-references/\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Muejeje test")
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return root, manifest_path


def commit_manifest(root: Path, manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    git(root, "add", str(manifest_path.relative_to(root)))
    git(root, "commit", "-qm", "update manifest")


def reference_entry(root: Path) -> dict[str, str]:
    path = root / REFERENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = b"synthetic API reference\n"
    path.write_bytes(contents)
    return {"path": REFERENCE_PATH, "sha256": hashlib.sha256(contents).hexdigest()}


# ---------------------------------------------------------------------------
# Measurement helpers for the architecture gates.
# ---------------------------------------------------------------------------

def source_lines(path: Path) -> int:
    """Physical lines. The budget is about how much file a reader must hold."""
    return len(path.read_text(encoding="utf-8").splitlines())


def python_function_lengths(path: Path) -> list[tuple[str, int]]:
    """`(name, code-line span)` for every def in a module, docstring excluded.

    The budget is about how much branching a reader must follow, not about how
    well it is explained. Counting the docstring would push a long explanation
    out of a function that needs one, so the docstring's own span is subtracted.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lengths: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        span = (node.end_lineno or node.lineno) - node.lineno + 1
        lengths.append((node.name, span - _docstring_span(node)))
    return lengths


def _docstring_span(node: ast.AST) -> int:
    body = getattr(node, "body", [])
    if not body:
        return 0
    first = body[0]
    if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
        return 0
    if not isinstance(first.value.value, str):
        return 0
    return (first.end_lineno or first.lineno) - first.lineno + 1


def js_function_lengths(path: Path) -> list[tuple[str, int]]:
    """`(name, physical line span)` for every top-level `function name(...)`.

    A brace counter, not a parser: the owned Script Engine sources are plain
    ES5 function declarations with no string or comment containing an unmatched
    brace, and the gate that keeps them that way is in the same test module.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    lengths: list[tuple[str, int]] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("function ") and stripped.endswith("{"):
            name = stripped[len("function "):].split("(")[0].strip()
            depth = 0
            start = index
            while index < len(lines):
                depth += lines[index].count("{") - lines[index].count("}")
                if depth == 0:
                    break
                index += 1
            lengths.append((name, index - start + 1))
        index += 1
    return lengths


def packaged_sources() -> list[Path]:
    suffixes = {".js", ".html", ".htm", ".css", ".png", ".gif", ".jpg", ".svg"}
    return sorted(
        path for path in SOURCE_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def engine_sources() -> list[Path]:
    return sorted(SCRIPT_ENGINE.glob("*.js"))


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()
