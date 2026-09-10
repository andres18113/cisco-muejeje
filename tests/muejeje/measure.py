"""Measurement over the real Muejeje tree, for the architecture gates.

Reading the tree and judging it are two responsibilities. This module reads:
it lists the owned sources, counts lines and function spans, resolves an import
to the sibling it names, and reports which files name a foreign layer. It
asserts nothing, so a claim always lives in the test module whose
responsibility it is (MJ-018, MJ-020).

It was split out of `support` when that module crossed its own line budget,
which is the budget doing what MJ-020 says it is for. `support` holds the
synthetic repository and the declared data; nothing here builds a fixture, and
nothing there measures a file.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from tests.muejeje.support import REPO_ROOT, SCRIPT_ENGINE, SOURCE_ROOT

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
