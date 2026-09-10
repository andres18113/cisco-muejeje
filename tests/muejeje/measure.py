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
import re
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


# A JavaScript comment, either spelling. The owned Script Engine sources are
# plain ES5 with no string that contains a comment opener, which is the same
# assumption the brace counter above already documents.
JS_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)


def js_code_only(body: str) -> str:
    """`body` with its comments removed, so a gate reads code and not prose.

    A boundary gate that read the comments would fire on the explanation of
    the boundary — every adapter header cites the platform calls it is allowed
    to make — and a gate that fires on its own explanation teaches people to
    delete the explanation rather than to keep the rule.
    """
    return JS_COMMENT.sub(" ", body)


# Packaged assets, split by whether their bytes are text. An asset is not text
# because it ships in the artifact: a `.png` is packaged and would raise on
# `read_text`, so every gate that reads prose reads `packaged_text_bodies()`
# and never the whole inventory. A suffix in neither set is unclassified, which
# is a gate failure rather than a default.
TEXT_SUFFIXES = frozenset({".js", ".html", ".htm", ".css", ".svg"})
BINARY_SUFFIXES = frozenset({".png", ".gif", ".jpg"})
PACKAGED_SUFFIXES = TEXT_SUFFIXES | BINARY_SUFFIXES


def packaged_sources(root: Path | None = None) -> list[Path]:
    """Every packageable asset under the owned root, text or not."""
    base = SOURCE_ROOT if root is None else root
    return sorted(
        path for path in base.rglob("*")
        if path.is_file() and path.suffix.lower() in PACKAGED_SUFFIXES
    )


def packaged_binary_sources(root: Path | None = None) -> list[Path]:
    """The packaged assets whose bytes are not text, and are never decoded."""
    return [
        path for path in packaged_sources(root)
        if path.suffix.lower() in BINARY_SUFFIXES
    ]


def packaged_text_bodies(root: Path | None = None) -> dict[str, str]:
    """`relative path -> decoded text` for the packaged assets that are text.

    Binary assets are absent rather than replaced by an empty string: a gate
    that swept them as "" would report a clean file it had never read.
    """
    return {
        relative(path): path.read_text(encoding="utf-8")
        for path in packaged_sources(root)
        if path.suffix.lower() in TEXT_SUFFIXES
    }


def engine_sources() -> list[Path]:
    return sorted(SCRIPT_ENGINE.glob("*.js"))


def relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        # A synthetic tree outside the checkout, used to assert that a gate can
        # fail. Its own name is enough to report it by.
        return path.name


def symbols_present(body: str, symbols: Iterable[str]) -> list[str]:
    """Which of `symbols` appear literally in `body`, case-insensitively.

    A vocabulary gate reduces to this question: does this file name a
    consumer's project or one topology's device. Keeping the measurement here
    and the *lists* in the test modules is what lets a test claim "this symbol
    belongs to that layer" instead of hiding it.
    """
    lowered = body.lower()
    return [symbol for symbol in symbols if symbol.lower() in lowered]


def literal_pattern(symbol: str) -> tuple[str, re.Pattern[str]]:
    """`symbol` named anywhere, case-insensitively: the substring rule."""
    return symbol, re.compile(re.escape(symbol), re.IGNORECASE)


def global_pattern(name: str) -> tuple[str, re.Pattern[str]]:
    """`name` used as a global — a member access `x.name` is not one.

    One spelling, two entirely different dependencies: PTBuilder supplies a
    global `addDevice(...)`, while Cisco documents `addDevice` as a member
    reached through `ipc`. A substring rule cannot tell them apart, so it must
    either forbid the official API — and be deleted the first time an adapter
    needs it — or admit the global it exists to keep out (MJ-013).
    """
    return name, re.compile(r"(?<![.\w$])" + re.escape(name) + r"\b")


def layer_offenders(
    bodies: dict[str, str],
    patterns: Iterable[tuple[str, re.Pattern[str]]],
    adapters: Iterable[str],
) -> list[str]:
    """`path: label` for every non-adapter file that names a foreign layer.

    A *declared* adapter is the one place a layer may be named, so the gate
    stays strict for the core without making an adapter impossible to add.
    Each pattern carries the label it is reported by, so a refusal names the
    symbol a reader would search for rather than a regular expression.
    """
    declared = set(adapters)
    patterns = list(patterns)
    return [
        f"{path}: {label}"
        for path, body in sorted(bodies.items())
        if path not in declared
        for label, pattern in patterns
        if pattern.search(body)
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
