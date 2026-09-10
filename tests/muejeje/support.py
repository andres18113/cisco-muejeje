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
from collections.abc import Iterable
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
    "src/packet_tracer_mcp/infrastructure/pts/references.py",
    "tools/build_muejeje_pts.py",
]

# Every kernel feature `MUEJEJE_CORE.SUPPORTED_FEATURES` may name, and the
# symbol in the artifact that backs it. Data, not a claim: the modules that
# assert against it are `test_runtime_identify` and `test_runtime_capabilities`
# for the reported list, and `test_unobserved_claims` for what a document may
# call a capability. It lives here because two copies of this map could
# disagree, and a feature backed by one of them would be a capability claim
# nobody was checking (MJ-028).
FEATURE_EVIDENCE = {
    "protocol.v6": ("validation_v6.js", "muejejeV6ParseRequest"),
    "runtime.operation_catalog": ("dispatcher_v6.js", "muejejeV6OperationCatalog"),
    "runtime.session_id": ("core.js", "muejejeCoreNewSessionId"),
}


def resolved_options() -> dict[str, Any]:
    """The baselined packaging recipe (MJ-025), read from the real manifest.

    The synthetic repository declares this repository's own artifact inputs,
    so its build options have to be this repository's own too: a fixture
    carrying its own copy of the engine order would keep the synthetic audit
    green after a reorder that no artifact reflects. `test_protocol_v6` is
    where the expected order is written down and asserted; here it is read.
    """
    return dict(repo_manifest()["build_options"])


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


def symbols_present(body: str, symbols: Iterable[str]) -> list[str]:
    """Which of `symbols` appear literally in `body`, case-insensitively.

    A layer gate and a vocabulary gate both reduce to this question. Keeping
    the measurement here and the *lists* in the test modules is what lets a
    test claim "this symbol belongs to that layer" instead of hiding it.
    """
    lowered = body.lower()
    return [symbol for symbol in symbols if symbol.lower() in lowered]


def layer_offenders(
    bodies: dict[str, str],
    symbols: Iterable[str],
    adapters: Iterable[str],
) -> list[str]:
    """`path: symbol` for every non-adapter file that names a foreign layer.

    A *declared* adapter is the one place a layer may be named, so the gate
    stays strict for the core without making an adapter impossible to add.
    """
    declared = set(adapters)
    symbols = list(symbols)
    return [
        f"{path}: {symbol}"
        for path, body in sorted(bodies.items())
        if path not in declared
        for symbol in symbols_present(body, symbols)
    ]


# The auditor package, as it is spelled in an absolute import. `pts` is the
# anchor: whatever follows it names a sibling, however the import was written.
PTS_PACKAGE_ANCHOR = "pts"


def imported_siblings(source: str, siblings: Iterable[str]) -> set[str]:
    """Sibling modules `source` imports, relative or absolute spelling alike.

    `from . import manifest`, `from .manifest import X`,
    `from ..pts import manifest`, `from a.b.pts.manifest import X` and
    `import a.b.pts.manifest` all reach the same module, so a dependency gate
    that reads only one of those spellings can be walked around by writing
    another.
    """
    known = set(siblings)
    reached: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        for path in _imported_paths(node):
            reached |= _siblings_on_path(path, known)
    return reached


def _imported_paths(node: ast.AST) -> list[list[str]]:
    """Every dotted path an import statement names, one list of parts each."""
    if isinstance(node, ast.Import):
        return [alias.name.split(".") for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    base = ["."] * node.level + (node.module.split(".") if node.module else [])
    return [base] + [base + [alias.name] for alias in node.names]


def _siblings_on_path(path: list[str], siblings: set[str]) -> set[str]:
    """A part is a sibling when the part before it anchors the package."""
    return {
        part for index, part in enumerate(path)
        if index and part in siblings
        and path[index - 1] in (".", PTS_PACKAGE_ANCHOR)
    }
