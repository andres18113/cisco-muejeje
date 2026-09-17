"""Prove that a changed Python file carries only an authorized mechanical migration.

The incremental Ruff gate treats every touched Python file as authored work. A
repository-wide mechanical migration, such as renaming an import namespace,
therefore drags each touched file's untouched historical debt into the current
change. This module supplies the missing distinction: it reconstructs the
candidate revision by applying a registered transformation to the base revision
and grants the `MECHANICAL_ONLY` classification only when the reconstruction is
exactly the candidate.

The classification is proven, never declared. A file cannot opt itself in, and an
unproven or unanalyzable comparison never yields an exemption. Every function here
is pure over the text and identifiers it receives; reading Git or the filesystem
belongs to the gate.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "AUTHORIZATION_SCHEMA",
    "AUTHORIZATION_VERSION",
    "AuditedDynamicSite",
    "Classification",
    "MechanicalAuthorization",
    "MechanicalMigrationError",
    "MechanicalTransformation",
    "Verdict",
    "classify_bytes_change",
    "classify_source_change",
    "namespace_transformation",
    "parse_authorization",
    "registered_identifiers",
    "resolve_transformations",
]

AUTHORIZATION_SCHEMA = "cisco-mcp/mechanical-migration-authorization"
AUTHORIZATION_VERSION = 1
MODULE_SCOPE = "<module>"


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
class AuditedDynamicSite:
    """Identify one dynamic module reference a human audit proved to be one.

    A callee's name does not establish what the name is bound to, so a string
    argument is rewritten only at a site registered here. The site is bound to its
    repository-relative path, to the SHA-256 of the exact base text it was audited
    in, and, inside that text, to its enclosing scope, callee, argument slot,
    legacy literal, and occurrence among identical references in that scope.
    """

    path: str
    base_sha256: str
    scope: str
    callee: str
    argument: int | str
    literal: str
    occurrence: int = 0


@dataclass(frozen=True)
class MechanicalTransformation:
    """Describe one registered, reviewed, purely mechanical source rewrite.

    `rewrite` receives the text to transform and its repository-relative path, or
    `None` when the path is unknown. `audited_sites` lists the dynamic sites the
    rewrite may touch and `audited_at` names the commit they were audited at.
    """

    identifier: str
    summary: str
    authority: str
    rewrite: Callable[[str, str | None], RewriteResult]
    audited_sites: tuple[AuditedDynamicSite, ...] = ()
    audited_at: str | None = None


@dataclass(frozen=True)
class MechanicalAuthorization:
    """Bind one registered transformation to the exact base it was authorized for."""

    source: str
    transformation: MechanicalTransformation
    base_commit: str
    authority: str

    def is_active_for(self, merge_base_sha: str) -> bool:
        """Return whether this record authorizes a comparison at this merge base."""
        return self.base_commit == merge_base_sha


@dataclass(frozen=True)
class _CallTarget:
    """Select the arguments of a recognized call that may name a module."""

    positions: tuple[int, ...]
    keywords: frozenset[str]


# The call shapes an audited dynamic site may take. Matching one of these grants
# nothing by itself: the name of a callee proves nothing about its binding, so a
# string argument is rewritten only at a registered `AuditedDynamicSite`.
_DYNAMIC_CALL_CONSTRUCTS: Mapping[str, _CallTarget] = {
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
_RELATIVE_POSIX_PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
# Python's tokenizer ends a line at CRLF, CR, or LF.
_LINE_TERMINATOR = re.compile(r"\r\n|\r|\n")


class _SourceIndex:
    """Convert AST positions into absolute offsets of the same source string."""

    def __init__(self, source: str) -> None:
        starts = [0]
        ends: list[int] = []
        for terminator in _LINE_TERMINATOR.finditer(source):
            ends.append(terminator.start())
            starts.append(terminator.end())
        ends.append(len(source))
        self._source = source
        self._starts = starts
        self._ends = ends

    def offset(self, lineno: int, column: int) -> int | None:
        """Return the absolute offset of a one-based line and UTF-8 column."""
        if lineno < 1 or lineno > len(self._starts):
            return None
        start = self._starts[lineno - 1]
        line = self._source[start : self._ends[lineno - 1]]
        try:
            prefix = line.encode("utf-8")[:column].decode("utf-8")
        except UnicodeDecodeError:
            return None
        return start + len(prefix)


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
    return tail == "" or tail[0] in ". \t\\\r\n"


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


def _scoped_nodes(tree: ast.AST) -> Iterator[tuple[str, ast.AST]]:
    """Yield every node with the qualified name of the def or class body holding it.

    Decorators, defaults, annotations, and base classes belong to the enclosing
    scope; only the statements of a body belong to the definition itself.
    """
    pending: list[tuple[ast.AST, tuple[str, ...]]] = [(tree, ())]
    while pending:
        node, scope = pending.pop()
        yield ".".join(scope) or MODULE_SCOPE, node
        defines_scope = isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        )
        for field, value in ast.iter_fields(node):
            inner = scope
            if defines_scope and field == "body":
                inner = (*scope, node.name)
            children = value if isinstance(value, list) else [value]
            pending.extend(
                (child, inner) for child in children if isinstance(child, ast.AST)
            )


def _dynamic_candidates(
    scope: str,
    node: ast.Call,
    legacy: str,
) -> Iterator[tuple[tuple[str, str, int | str, str], ast.Constant]]:
    """Yield the namespace literals a recognized call shape passes as a module."""
    callee = _callee_name(node.func)
    construct = _DYNAMIC_CALL_CONSTRUCTS.get(callee) if callee else None
    if callee is None or construct is None:
        return
    arguments: list[tuple[int | str, ast.expr]] = [
        (position, node.args[position])
        for position in construct.positions
        if position < len(node.args)
        and not isinstance(node.args[position], ast.Starred)
    ]
    arguments.extend(
        (keyword.arg, keyword.value)
        for keyword in node.keywords
        if keyword.arg is not None and keyword.arg in construct.keywords
    )
    for argument, value in arguments:
        if (
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and _is_namespace_reference(value.value, legacy)
        ):
            yield (scope, callee, argument, value.value), value


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


def _validate_audited_site(site: AuditedDynamicSite, legacy: str) -> None:
    """Reject an audited site that no exact base site could ever match."""
    construct = _DYNAMIC_CALL_CONSTRUCTS.get(site.callee)
    if construct is None:
        raise MechanicalMigrationError(
            f"Audited site in {site.path!r} uses unrecognized construct "
            f"{site.callee!r}."
        )
    argument = site.argument
    if isinstance(argument, bool) or not (
        (isinstance(argument, int) and argument in construct.positions)
        or (isinstance(argument, str) and argument in construct.keywords)
    ):
        raise MechanicalMigrationError(
            f"Audited site in {site.path!r} names argument {argument!r}, which "
            f"{site.callee!r} does not pass as a module."
        )
    if not _is_namespace_reference(site.literal, legacy):
        raise MechanicalMigrationError(
            f"Audited site in {site.path!r} does not name {legacy!r}."
        )
    if not _SHA256.fullmatch(site.base_sha256):
        raise MechanicalMigrationError(
            f"Audited site in {site.path!r} needs a full lowercase SHA-256."
        )
    if not _RELATIVE_POSIX_PATH.fullmatch(site.path) or ".." in site.path.split("/"):
        raise MechanicalMigrationError(
            f"Audited site path {site.path!r} is not repository-relative."
        )
    if not site.scope:
        raise MechanicalMigrationError(f"Audited site in {site.path!r} has no scope.")
    if isinstance(site.occurrence, bool) or not isinstance(site.occurrence, int):
        raise MechanicalMigrationError(
            f"Audited site in {site.path!r} has a non-integer occurrence."
        )
    if site.occurrence < 0:
        raise MechanicalMigrationError(
            f"Audited site in {site.path!r} has a negative occurrence."
        )


def _build_namespace_rewrite(
    legacy: str,
    canonical: str,
    audited_sites: Sequence[AuditedDynamicSite],
) -> Callable[[str, str | None], RewriteResult]:
    """Build a rewrite that renames one import namespace at authorized sites only.

    Import statements are recognized structurally in any file. A dynamic string is
    rewritten only when the file's path and exact base text match an audited site
    and the site's scope, callee, argument, literal, and occurrence match too.
    """
    audited: dict[tuple[str, str], set[tuple[str, str, int | str, str, int]]] = {}
    for site in audited_sites:
        audited.setdefault((site.path, site.base_sha256), set()).add(
            (site.scope, site.callee, site.argument, site.literal, site.occurrence)
        )

    def rewrite(source: str, path: str | None) -> RewriteResult:
        tree = ast.parse(source)
        index = _SourceIndex(source)
        sites: list[RewriteSite] = []
        calls: list[tuple[str, ast.Call]] = []
        for scope, node in _scoped_nodes(tree):
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
                calls.append((scope, node))

        fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()
        authorized = audited.get((path, fingerprint), set()) if path else set()
        if authorized:
            candidates = sorted(
                (
                    candidate
                    for scope, node in calls
                    for candidate in _dynamic_candidates(scope, node, legacy)
                ),
                key=lambda item: (item[1].lineno, item[1].col_offset),
            )
            occurrences: dict[tuple[str, str, int | str, str], int] = {}
            for key, value in candidates:
                occurrence = occurrences.get(key, 0)
                occurrences[key] = occurrence + 1
                if (*key, occurrence) not in authorized:
                    continue
                site = _literal_site(source, index, value, legacy, canonical)
                if site is not None:
                    sites.append(site)
        return RewriteResult(_apply(source, sites), tuple(sites))

    return rewrite


def namespace_transformation(
    identifier: str,
    summary: str,
    authority: str,
    legacy: str,
    canonical: str,
    audited_sites: Sequence[AuditedDynamicSite] = (),
    audited_at: str | None = None,
) -> MechanicalTransformation:
    """Build a namespace rename honoring imports and exactly the audited sites.

    Raises `MechanicalMigrationError` when an audited site could never match an
    exact base site, so an invalid registry fails when it is built.
    """
    sites = tuple(audited_sites)
    for site in sites:
        _validate_audited_site(site, legacy)
    return MechanicalTransformation(
        identifier=identifier,
        summary=summary,
        authority=authority,
        rewrite=_build_namespace_rewrite(legacy, canonical, sites),
        audited_sites=sites,
        audited_at=audited_at,
    )


# Dynamic references to the legacy namespace at the authorized base, inventoried
# and audited at the commit below. Each callee is bound in its own file by
# `import importlib`, `import importlib.util`, `from importlib.util import
# find_spec`, or the `__import__` builtin, with no rebinding in that file. The base
# also holds one implicitly concatenated `monkeypatch.setattr` target in
# tests/test_poe_delivery_qualification.py; the boundary never rewrites such a
# literal, so it is deliberately absent.
_CANONICAL_NAMESPACE_AUDITED_AT = "5330e0dd424bfa746007034ba0672e570cc4ff0f"
_CANONICAL_NAMESPACE_SITES = (
    AuditedDynamicSite(
        path="tests/test_cp_scale_live_cli.py",
        base_sha256="aee16b7420fe18cf90158b7226843d5b949a34abce02d79131596d7f0162e15b",
        scope="test_persistence_uses_the_composed_root_and_hashes_the_actual_progress",
        callee="importlib.util.find_spec",
        argument=0,
        literal="src.packet_tracer_mcp.infrastructure.persistence.cp_scale_live",
    ),
    AuditedDynamicSite(
        path="tests/test_cp_scale_live_coordinator.py",
        base_sha256="b1ee91d38e1ed2099d50308c153c5bff5249b6c46945cf3794c27f4cfd9b8275",
        scope="test_application_coordinator_is_available_without_loading_the_tool",
        callee="importlib.util.find_spec",
        argument=0,
        literal="src.packet_tracer_mcp.application.cp_scale_live.coordinator",
    ),
    AuditedDynamicSite(
        path="tests/test_cp_scale_live_coordinator.py",
        base_sha256="b1ee91d38e1ed2099d50308c153c5bff5249b6c46945cf3794c27f4cfd9b8275",
        scope="test_partial_session_acquisition_closes_the_acquired_transport_once",
        callee="importlib.util.find_spec",
        argument=0,
        literal="src.packet_tracer_mcp.infrastructure.execution.cp_scale_live_session",
    ),
    AuditedDynamicSite(
        path="tests/test_cp_scale_live_coordinator.py",
        base_sha256="b1ee91d38e1ed2099d50308c153c5bff5249b6c46945cf3794c27f4cfd9b8275",
        scope="test_session_reuses_resources_and_marks_close_before_a_failing_stop",
        callee="importlib.util.find_spec",
        argument=0,
        literal="src.packet_tracer_mcp.infrastructure.execution.cp_scale_live_session",
    ),
    AuditedDynamicSite(
        path="tests/test_cp_scale_stage_executor.py",
        base_sha256="f2de4500b7b081ce17c8eac86fc19e0856cd50da018cf4e5715da9cb3f93b261",
        scope="_api",
        callee="find_spec",
        argument=0,
        literal="src.packet_tracer_mcp.application.cp_scale_live.stage_executor",
    ),
    AuditedDynamicSite(
        path="tests/test_cp_scale_stage_executor.py",
        base_sha256="f2de4500b7b081ce17c8eac86fc19e0856cd50da018cf4e5715da9cb3f93b261",
        scope="test_ping_result_is_the_same_neutral_value_at_the_legacy_import",
        callee="find_spec",
        argument=0,
        literal="src.packet_tracer_mcp.domain.models.typed_ping",
    ),
    AuditedDynamicSite(
        path="tests/test_e95_e5_capability_evidence.py",
        base_sha256="9aa9540794b26909a245a21557b19980cc3af925723a88e05eee82ecac162463",
        scope="test_default_execution_materializes_one_catalog_for_both_compositions",
        callee="importlib.import_module",
        argument=0,
        literal="src.packet_tracer_mcp.application.use_cases.plan_enterprise_hardware",
    ),
    AuditedDynamicSite(
        path="tests/test_mutation_transport_ambiguity.py",
        base_sha256="9df4851393a89068fa63ccdbe5d97a5c1fe98f9aa36a2c4326f53d51d5f6ac9b",
        scope="test_the_connectivity_tool_budget_meets_the_floor",
        callee="__import__",
        argument=0,
        literal="src.packet_tracer_mcp.adapters.mcp.tool_registry",
    ),
)

# The registry is the only source of authority. A transformation exists because
# it is reviewed and committed here, never because a run, a branch, an
# authorization record, or a file claims it.
MECHANICAL_TRANSFORMATIONS: Mapping[str, MechanicalTransformation] = {
    "CANONICAL_PYTHON_NAMESPACE": namespace_transformation(
        identifier="CANONICAL_PYTHON_NAMESPACE",
        summary=(
            "Rename the retired src.packet_tracer_mcp import namespace to "
            "packet_tracer_mcp at import statements and audited dynamic import "
            "sites."
        ),
        authority="docs/engineering/change-briefs/namespace-migration.md",
        legacy="src.packet_tracer_mcp",
        canonical="packet_tracer_mcp",
        audited_sites=_CANONICAL_NAMESPACE_SITES,
        audited_at=_CANONICAL_NAMESPACE_AUDITED_AT,
    ),
}


def registered_identifiers() -> tuple[str, ...]:
    """Return every registered transformation identifier in a stable order."""
    return tuple(sorted(MECHANICAL_TRANSFORMATIONS))


def resolve_transformations(
    identifiers: Iterable[str],
) -> tuple[MechanicalTransformation, ...]:
    """Resolve requested identifiers in registry order, rejecting unregistered ones."""
    requested: set[str] = set()
    for identifier in identifiers:
        if identifier not in MECHANICAL_TRANSFORMATIONS:
            known = ", ".join(registered_identifiers()) or "none"
            raise MechanicalMigrationError(
                f"Unregistered mechanical migration {identifier!r}; registered: {known}."
            )
        requested.add(identifier)
    return tuple(
        transformation
        for identifier, transformation in MECHANICAL_TRANSFORMATIONS.items()
        if identifier in requested
    )


class _DuplicateField(ValueError):
    """Report a JSON object that names one field more than once."""


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object, rejecting a field whose later value would hide another."""
    record: dict[str, object] = {}
    for key, value in pairs:
        if key in record:
            raise _DuplicateField(f"duplicate field {key!r}")
        record[key] = value
    return record


_AUTHORIZATION_FIELDS = (
    "schema",
    "version",
    "transformation",
    "base_commit",
    "authority",
)


def parse_authorization(source: str, data: bytes) -> MechanicalAuthorization:
    """Parse one committed authorization record, failing closed on any defect.

    The record must be a UTF-8 JSON object holding exactly the fields `schema`,
    `version`, `transformation`, `base_commit`, and `authority`. It may only name
    a registered transformation, bind it to one full lowercase commit SHA, and
    cite that transformation's registered authority. Raises
    `MechanicalMigrationError` otherwise.
    """

    def invalid(detail: str) -> MechanicalMigrationError:
        return MechanicalMigrationError(
            f"Mechanical authorization {source!r} is invalid: {detail}."
        )

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise invalid("it is not UTF-8") from error
    try:
        record = json.loads(text, object_pairs_hook=_unique_fields)
    except ValueError as error:
        raise invalid(f"it is not one JSON object ({error})") from error
    if not isinstance(record, dict):
        raise invalid("it is not a JSON object")
    for field in _AUTHORIZATION_FIELDS:
        if field not in record:
            raise invalid(f"missing required field {field!r}")
    unknown = sorted(set(record) - set(_AUTHORIZATION_FIELDS))
    if unknown:
        raise invalid(
            f"unknown field {unknown[0]!r}; a record cannot extend the registry"
        )
    if record["schema"] != AUTHORIZATION_SCHEMA:
        raise invalid(f"schema must be {AUTHORIZATION_SCHEMA!r}")
    version = record["version"]
    if type(version) is not int or version != AUTHORIZATION_VERSION:
        raise invalid(f"version must be the integer {AUTHORIZATION_VERSION}")
    identifier = record["transformation"]
    if not isinstance(identifier, str):
        raise invalid("transformation must be one registered identifier")
    transformation = MECHANICAL_TRANSFORMATIONS.get(identifier)
    if transformation is None:
        raise invalid(f"unregistered transformation {identifier!r}")
    base_commit = record["base_commit"]
    if not isinstance(base_commit, str) or not _COMMIT_SHA.fullmatch(base_commit):
        raise invalid("base_commit must be a full lowercase commit SHA")
    authority = record["authority"]
    if authority != transformation.authority:
        raise invalid(
            f"authority must be the registered brief {transformation.authority!r}"
        )
    return MechanicalAuthorization(
        source=source,
        transformation=transformation,
        base_commit=base_commit,
        authority=transformation.authority,
    )


def classify_source_change(
    base_source: str | None,
    candidate_source: str,
    transformations: Sequence[MechanicalTransformation],
    path: str | None = None,
) -> Verdict:
    """Classify a Python file's delta against the authorized transformations.

    The comparison is exact: line terminators and whitespace are compared as
    given. `path` is the file's repository-relative POSIX path; without it no
    audited dynamic site can match.
    """
    if base_source is None:
        return Verdict(Classification.NEW_FILE, "The file has no base revision.")

    if base_source == candidate_source:
        return Verdict(Classification.UNCHANGED, "The revisions are identical.")
    if not transformations:
        return Verdict(
            Classification.SEMANTIC_OR_AUTHORED_CHANGE,
            "No mechanical migration is authorized for this comparison.",
        )

    identifiers = tuple(item.identifier for item in transformations)
    expected = base_source
    applied = 0
    try:
        for transformation in transformations:
            result = transformation.rewrite(expected, path)
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
    if expected != candidate_source:
        return Verdict(
            Classification.SEMANTIC_OR_AUTHORED_CHANGE,
            "The delta exceeds the authorized mechanical transformation.",
            applied_sites=applied,
            transformations=identifiers,
        )
    try:
        ast.parse(candidate_source)
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
    path: str | None = None,
) -> Verdict:
    """Decode both revisions and classify them, failing closed on undecodable bytes.

    Strict UTF-8 decoding is injective, so equal decoded texts mean equal bytes.
    """
    try:
        candidate_source = candidate_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return Verdict(
            Classification.UNVERIFIABLE,
            "The candidate revision is not decodable UTF-8.",
        )
    if base_bytes is None:
        return classify_source_change(None, candidate_source, transformations, path)
    try:
        base_source = base_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return Verdict(
            Classification.UNVERIFIABLE,
            "The base revision is not decodable UTF-8.",
        )
    return classify_source_change(base_source, candidate_source, transformations, path)
