"""Prove that a changed Python file carries only an authorized mechanical migration.

The incremental Ruff gate treats every touched Python file as authored work. A
repository-wide mechanical migration, such as renaming an import namespace,
therefore drags each touched file's untouched historical debt into the current
change. This module supplies the missing distinction: it reconstructs the
candidate revision by applying a registered transformation to the base revision
and grants the `MECHANICAL_ONLY` classification only when the reconstruction is
exactly the candidate.

The classification is proven, never declared. A file cannot opt itself in, and an
unproven or unanalyzable comparison never yields an exemption.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "Classification",
    "MechanicalMigrationError",
    "MechanicalTransformation",
    "Verdict",
    "classify_bytes_change",
    "classify_source_change",
    "registered_identifiers",
    "resolve_transformations",
]


class MechanicalMigrationError(RuntimeError):
    """Report a transformation request that cannot be honored."""


class Classification(Enum):
    """Name the boundary decision taken for one changed Python file."""

    NEW_FILE = "NEW_FILE"
    UNCHANGED = "UNCHANGED"
    MECHANICAL_ONLY = "MECHANICAL_ONLY"
    SEMANTIC_OR_AUTHORED_CHANGE = "SEMANTIC_OR_AUTHORED_CHANGE"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class Verdict:
    """Record one file's classification together with the reason behind it."""

    classification: Classification
    reason: str
    applied_sites: int = 0
    transformations: tuple[str, ...] = ()

    @property
    def is_exempt(self) -> bool:
        """Return whether this verdict removes the file from the Ruff gate."""
        return self.classification in {
            Classification.MECHANICAL_ONLY,
            Classification.UNCHANGED,
        }


@dataclass(frozen=True)
class RewriteSite:
    """Locate one authorized rewrite inside the base revision's source text."""

    start: int
    end: int
    replacement: str
    kind: str


@dataclass(frozen=True)
class RewriteResult:
    """Carry a rewritten source together with the sites that produced it."""

    source: str
    sites: tuple[RewriteSite, ...]


@dataclass(frozen=True)
class MechanicalTransformation:
    """Describe one registered, reviewed, purely mechanical source rewrite."""

    identifier: str
    summary: str
    authority: str
    rewrite: Callable[[str], RewriteResult]


@dataclass(frozen=True)
class _CallTarget:
    """Select the arguments of a recognized call that may name a module."""

    positions: tuple[int, ...]
    keywords: frozenset[str]


# Only these callables have their string arguments treated as module references.
# Anything absent is unauthorized, so its rewrite makes the file authored work.
_AUTHORIZED_CALL_TARGETS: Mapping[str, _CallTarget] = {
    "__import__": _CallTarget((0,), frozenset({"name"})),
    "import_module": _CallTarget((0,), frozenset({"name"})),
    "importlib.import_module": _CallTarget((0,), frozenset({"name"})),
    "find_spec": _CallTarget((0,), frozenset({"name"})),
    "importlib.util.find_spec": _CallTarget((0,), frozenset({"name"})),
    "patch": _CallTarget((0,), frozenset({"target"})),
    "mock.patch": _CallTarget((0,), frozenset({"target"})),
    "unittest.mock.patch": _CallTarget((0,), frozenset({"target"})),
    "monkeypatch.setattr": _CallTarget((0,), frozenset()),
    "monkeypatch.delattr": _CallTarget((0,), frozenset()),
}

# A module reference written as a plain single-quoted literal with no prefix, no
# escape and no implicit concatenation. Anything richer stays unauthorized.
_PLAIN_MODULE_LITERAL = re.compile(r"(['\"])([A-Za-z0-9_.]*)\1")


class _SourceIndex:
    """Convert AST positions into absolute offsets of the same source string."""

    def __init__(self, source: str) -> None:
        lines = source.split("\n")
        offsets: list[int] = []
        total = 0
        for line in lines:
            offsets.append(total)
            total += len(line) + 1
        self._lines = lines
        self._offsets = offsets

    def offset(self, lineno: int, column: int) -> int | None:
        """Return the absolute offset of a one-based line and UTF-8 column."""
        if lineno < 1 or lineno > len(self._lines):
            return None
        line = self._lines[lineno - 1]
        try:
            prefix = line.encode("utf-8")[:column].decode("utf-8")
        except UnicodeDecodeError:
            return None
        return self._offsets[lineno - 1] + len(prefix)


def _span(index: _SourceIndex, node: ast.AST) -> tuple[int, int] | None:
    """Return a node's absolute source span when it is fully positioned."""
    lineno = getattr(node, "lineno", None)
    col_offset = getattr(node, "col_offset", None)
    end_lineno = getattr(node, "end_lineno", None)
    end_col_offset = getattr(node, "end_col_offset", None)
    if None in (lineno, col_offset, end_lineno, end_col_offset):
        return None
    start = index.offset(lineno, col_offset)
    end = index.offset(end_lineno, end_col_offset)
    if start is None or end is None or end < start:
        return None
    return start, end


def _is_namespace_reference(value: str, legacy: str) -> bool:
    """Return whether a dotted name is the legacy namespace or lives inside it."""
    return value == legacy or value.startswith(f"{legacy}.")


def _tail_is_a_boundary(tail: str) -> bool:
    """Return whether the text after a dotted prefix ends that prefix cleanly."""
    return tail == "" or tail[0] in ". \t\\\n"


def _alias_site(
    source: str,
    index: _SourceIndex,
    alias: ast.alias,
    legacy: str,
    canonical: str,
) -> RewriteSite | None:
    """Authorize the dotted name of an `import legacy.module` statement."""
    if not _is_namespace_reference(alias.name, legacy):
        return None
    span = _span(index, alias)
    if span is None:
        return None
    start, end = span
    segment = source[start:end]
    if not segment.startswith(legacy):
        return None
    if not _tail_is_a_boundary(segment[len(legacy) :]):
        return None
    return RewriteSite(start, start + len(legacy), canonical, "import")


def _module_site(
    source: str,
    index: _SourceIndex,
    node: ast.ImportFrom,
    legacy: str,
    canonical: str,
) -> RewriteSite | None:
    """Authorize the module of a `from legacy.module import name` statement."""
    if node.level != 0 or node.module is None:
        return None
    if not _is_namespace_reference(node.module, legacy):
        return None
    span = _span(index, node)
    if span is None:
        return None
    start, end = span
    segment = source[start:end]
    match = re.match(rf"from[ \t]+{re.escape(legacy)}", segment)
    if match is None:
        return None
    if not _tail_is_a_boundary(segment[match.end() :]):
        return None
    module_start = start + match.end() - len(legacy)
    return RewriteSite(module_start, module_start + len(legacy), canonical, "from")


def _callee_name(func: ast.expr) -> str | None:
    """Return the dotted source name of a call's callee, when it is a plain name."""
    parts: list[str] = []
    current: ast.expr = func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _literal_site(
    source: str,
    index: _SourceIndex,
    node: ast.expr,
    legacy: str,
    canonical: str,
) -> RewriteSite | None:
    """Authorize a recognized call argument that names a module as a literal."""
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return None
    if not _is_namespace_reference(node.value, legacy):
        return None
    span = _span(index, node)
    if span is None:
        return None
    start, end = span
    segment = source[start:end]
    match = _PLAIN_MODULE_LITERAL.fullmatch(segment)
    if match is None or match.group(2) != node.value:
        return None
    return RewriteSite(start + 1, start + 1 + len(legacy), canonical, "call-argument")


def _call_argument_sites(
    source: str,
    index: _SourceIndex,
    node: ast.Call,
    legacy: str,
    canonical: str,
) -> list[RewriteSite]:
    """Authorize the module-naming arguments of one recognized call."""
    name = _callee_name(node.func)
    if name is None:
        return []
    target = _AUTHORIZED_CALL_TARGETS.get(name)
    if target is None:
        return []
    candidates: list[ast.expr] = [
        node.args[position]
        for position in target.positions
        if position < len(node.args)
        and not isinstance(node.args[position], ast.Starred)
    ]
    candidates.extend(
        keyword.value
        for keyword in node.keywords
        if keyword.arg is not None and keyword.arg in target.keywords
    )
    sites: list[RewriteSite] = []
    for candidate in candidates:
        site = _literal_site(source, index, candidate, legacy, canonical)
        if site is not None:
            sites.append(site)
    return sites


def _apply(source: str, sites: Sequence[RewriteSite]) -> str:
    """Splice every authorized site into the source, rejecting overlaps."""
    ordered = sorted(sites, key=lambda site: site.start)
    pieces: list[str] = []
    cursor = 0
    for site in ordered:
        if site.start < cursor:
            raise MechanicalMigrationError(
                "Overlapping mechanical rewrite sites cannot be applied."
            )
        pieces.append(source[cursor : site.start])
        pieces.append(site.replacement)
        cursor = site.end
    pieces.append(source[cursor:])
    return "".join(pieces)


def _build_namespace_rewrite(
    legacy: str,
    canonical: str,
) -> Callable[[str], RewriteResult]:
    """Build a rewrite that renames one import namespace at authorized sites only."""

    def rewrite(source: str) -> RewriteResult:
        tree = ast.parse(source)
        index = _SourceIndex(source)
        sites: list[RewriteSite] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    site = _alias_site(source, index, alias, legacy, canonical)
                    if site is not None:
                        sites.append(site)
            elif isinstance(node, ast.ImportFrom):
                module = _module_site(source, index, node, legacy, canonical)
                if module is not None:
                    sites.append(module)
            elif isinstance(node, ast.Call):
                sites.extend(
                    _call_argument_sites(source, index, node, legacy, canonical)
                )
        return RewriteResult(_apply(source, sites), tuple(sites))

    return rewrite


# The registry is the only source of authority. A transformation exists because
# it is reviewed and committed here, never because a run, a branch or a file
# claims it.
MECHANICAL_TRANSFORMATIONS: Mapping[str, MechanicalTransformation] = {
    "CANONICAL_PYTHON_NAMESPACE": MechanicalTransformation(
        identifier="CANONICAL_PYTHON_NAMESPACE",
        summary=(
            "Rename the retired src.packet_tracer_mcp import namespace to "
            "packet_tracer_mcp at import statements and recognized dynamic "
            "import and patch targets."
        ),
        authority="docs/engineering/change-briefs/namespace-migration.md",
        rewrite=_build_namespace_rewrite("src.packet_tracer_mcp", "packet_tracer_mcp"),
    ),
}


def registered_identifiers() -> tuple[str, ...]:
    """Return every registered transformation identifier in a stable order."""
    return tuple(sorted(MECHANICAL_TRANSFORMATIONS))


def resolve_transformations(
    identifiers: Iterable[str],
) -> tuple[MechanicalTransformation, ...]:
    """Resolve requested identifiers, rejecting any that is not registered."""
    resolved: list[MechanicalTransformation] = []
    seen: set[str] = set()
    for identifier in identifiers:
        transformation = MECHANICAL_TRANSFORMATIONS.get(identifier)
        if transformation is None:
            known = ", ".join(registered_identifiers()) or "none"
            raise MechanicalMigrationError(
                f"Unregistered mechanical migration {identifier!r}; registered: {known}."
            )
        if identifier in seen:
            continue
        seen.add(identifier)
        resolved.append(transformation)
    return tuple(resolved)


def _normalize(source: str) -> str:
    """Normalize line terminators so checkout filters cannot affect the proof."""
    return source.replace("\r\n", "\n").replace("\r", "\n")


def classify_source_change(
    base_source: str | None,
    candidate_source: str,
    transformations: Sequence[MechanicalTransformation],
) -> Verdict:
    """Classify a Python file's delta against the authorized transformations."""
    if base_source is None:
        return Verdict(Classification.NEW_FILE, "The file has no base revision.")

    base = _normalize(base_source)
    candidate = _normalize(candidate_source)
    if base == candidate:
        return Verdict(Classification.UNCHANGED, "The revisions are identical.")
    if not transformations:
        return Verdict(
            Classification.SEMANTIC_OR_AUTHORED_CHANGE,
            "No mechanical migration is authorized for this comparison.",
        )

    identifiers = tuple(item.identifier for item in transformations)
    expected = base
    applied = 0
    try:
        for transformation in transformations:
            result = transformation.rewrite(expected)
            expected = result.source
            applied += len(result.sites)
    except SyntaxError:
        return Verdict(
            Classification.SEMANTIC_OR_AUTHORED_CHANGE,
            "The base revision is not parseable Python.",
        )
    except MechanicalMigrationError as error:
        return Verdict(
            Classification.SEMANTIC_OR_AUTHORED_CHANGE,
            f"The authorized rewrite could not be applied: {error}",
        )

    if applied == 0:
        return Verdict(
            Classification.SEMANTIC_OR_AUTHORED_CHANGE,
            "The base revision holds no authorized mechanical site.",
            transformations=identifiers,
        )
    if expected != candidate:
        return Verdict(
            Classification.SEMANTIC_OR_AUTHORED_CHANGE,
            "The delta exceeds the authorized mechanical transformation.",
            applied_sites=applied,
            transformations=identifiers,
        )
    try:
        ast.parse(candidate)
    except SyntaxError:
        return Verdict(
            Classification.SEMANTIC_OR_AUTHORED_CHANGE,
            "The candidate revision is not parseable Python.",
            transformations=identifiers,
        )
    return Verdict(
        Classification.MECHANICAL_ONLY,
        "The delta equals the authorized mechanical transformation.",
        applied_sites=applied,
        transformations=identifiers,
    )


def classify_bytes_change(
    base_bytes: bytes | None,
    candidate_bytes: bytes,
    transformations: Sequence[MechanicalTransformation],
) -> Verdict:
    """Decode both revisions and classify them, failing closed on undecodable bytes."""
    try:
        candidate_source = candidate_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return Verdict(
            Classification.UNVERIFIABLE,
            "The candidate revision is not decodable UTF-8.",
        )
    if base_bytes is None:
        return classify_source_change(None, candidate_source, transformations)
    try:
        base_source = base_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return Verdict(
            Classification.UNVERIFIABLE,
            "The base revision is not decodable UTF-8.",
        )
    return classify_source_change(base_source, candidate_source, transformations)
