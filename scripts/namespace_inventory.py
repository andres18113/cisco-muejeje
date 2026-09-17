"""Inventory every use of the retired `src.packet_tracer_mcp` import namespace.

The migration's acceptance criterion is not "the text disappeared": a handful of
places must keep naming the retired namespace, because their job is to reject
it. What must be zero is *executable* use -- anything that would load or register
the package under a second name.

Each mention is classified by its syntactic context, never by the file it is in:

import statements
    `import src...`, `from src.packet_tracer_mcp... import ...`, and
    `from src import ...` load the retired package in the process that runs them.

dynamic imports
    A string naming the retired namespace passed to a callable that imports or
    patches by name -- `import_module`, `find_spec`, `__import__`, `patch`,
    `monkeypatch.setattr`, and the like. Callees are matched by their last name,
    so any spelling of them counts, including a shadowed one: a false positive
    here can only make the inventory stricter.

module registry
    A string naming the retired namespace used to add an entry to `sys.modules`,
    by assignment, `setdefault`, `update`, `monkeypatch.setitem`, or
    `mock.patch.dict`. That creates the second name without importing anything.

executed source
    Source text passed to `exec`, `eval`, or `compile`, or following `-c` in an
    argument list, when that text itself contains one of the references above.
    A name assigned a string constant in the same file is resolved, so source
    kept in a constant and launched later is analyzed too. Source text in such a
    position that cannot be parsed is treated as executable.

These four kinds are *active*, and no allowlist entry can change that.

Every other string constant that names the retired namespace is an *inert*
mention: a guard's list of forbidden names, the subject of an assertion, a
lookup in `sys.modules`, or source text used as data. Inert mentions are allowed
only in the files listed in `RETAINED_STRING_REFERENCES`, each with the reason it
is retained, and an inert mention anywhere else is *unreviewed* and fails the
inventory. Docstrings and comments are reported as prose and never fail it.

The inventory reads literal text. A module name assembled at run time from
separate pieces is outside what any static scan can see; the refusal in
`src/__init__.py` holds that boundary at run time.

Exit status: 0 when nothing active or unreviewed remains, 1 when anything does,
and 2 when a file could not be parsed, which is unresolved and therefore a
failure rather than an empty answer.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

#: The retired import namespace this inventory looks for.
LEGACY_NAMESPACE = "src.packet_tracer_mcp"
#: Its package root, which is equally unusable as an import name.
LEGACY_ROOT = "src"

#: Callables whose string argument is a module name; even the bare root counts.
MODULE_NAME_CALLEES = frozenset(
    {
        "__import__",
        "find_loader",
        "find_spec",
        "get_loader",
        "import_module",
        "locate",
        "resolve_name",
        "run_module",
        "spec_from_file_location",
        "spec_from_loader",
    }
)
#: Callables whose dotted string argument imports its module to reach a target.
TARGET_PATH_CALLEES = frozenset({"delattr", "patch", "setattr"})
#: Methods of `sys.modules` that add an entry to it.
REGISTRY_METHODS = frozenset({"__setitem__", "setdefault", "update"})
#: Callables that add an entry to the mapping given as their first argument.
REGISTRY_CALLEES = frozenset({"dict", "setitem"})
#: Callables that execute the Python source given as their first argument.
SOURCE_EXECUTORS = frozenset({"compile", "eval", "exec"})

#: Files allowed to keep inert mentions of the retired name, and why.
#: Adding one is a decision: it must not be a way to park a real use, and an
#: entry grants nothing to an active reference in the same file.
RETAINED_STRING_REFERENCES: dict[str, str] = {
    "scripts/namespace_inventory.py": (
        "This inventory declares the name it searches for."
    ),
    "scripts/mechanical_migration.py": (
        "The registered CANONICAL_PYTHON_NAMESPACE transformation names the "
        "namespace it renames and the audited base sites it may rewrite."
    ),
    "src/__init__.py": (
        "The import refusal names the retired namespace in its diagnostic."
    ),
    "src/packet_tracer_mcp/infrastructure/execution/import_isolation_preflight.py": (
        "The LIVE gate names the retired namespace to reject it."
    ),
    "tests/namespace_preflight.py": (
        "The suite's fail-closed gate names the retired namespace to reject it."
    ),
    "tests/mechanical_migration_fixtures.py": (
        "Pre-migration source used as data by the mechanical boundary tests."
    ),
    "tests/test_mechanical_dynamic_site_authority.py": (
        "Source and audited-site data proving the boundary's dynamic authority."
    ),
    "tests/test_mechanical_migration_boundary.py": (
        "Source pairs proving what the mechanical rename may and may not rewrite."
    ),
    "tests/test_import_isolation_preflight.py": (
        "Proves the LIVE gate refuses a dual identity."
    ),
    "tests/test_cp_scale_live_local_preflight.py": (
        "Exercises the DUAL_IDENTITY refusal with both names present."
    ),
    "tests/test_cp_live_m0_reference_recording.py": (
        "Proves a recording is refused when a probe loaded the retired name."
    ),
    "tests/cp_live_m0_harness.py": (
        "Child-process provenance lists both names to detect a mixture."
    ),
    "tests/test_cp_live_m0_equivalence_baseline.py": (
        "Runtime tripwire asserting the parent holds one identity and not the "
        "retired one."
    ),
    "tests/test_cp_scale_live_failure_evidence.py": (
        "Runtime tripwire asserting one identity in a LIVE-adjacent file."
    ),
    "tests/test_cp_scale_voice_staging.py": (
        "Runtime tripwire asserting one identity in a LIVE-adjacent file."
    ),
    "tools/cp_scale_dhcp_pool_qualification_live.py": (
        "LIVE runner identity guard listing the forbidden names."
    ),
    "tools/cp_scale_positive_voice_ab_live.py": (
        "LIVE runner identity guard listing the forbidden names."
    ),
    "tools/cp_scale_routing_core_live.py": (
        "LIVE runner identity guard listing the forbidden names."
    ),
    "tools/eigrp_runtime_qualification.py": (
        "LIVE runner identity guard listing the forbidden names."
    ),
    "tools/poe2_ap_live.py": (
        "LIVE runner identity guard listing the forbidden names."
    ),
    "tools/poe3a_pse_live.py": (
        "LIVE runner identity guard listing the forbidden names."
    ),
    "tools/stp_pvst_runtime_qualification.py": (
        "LIVE runner identity guard listing the forbidden names."
    ),
}

#: Syntax that builds one string, so a constant inside it is still that string.
_STRING_BUILDERS = (ast.BinOp, ast.JoinedStr)
#: Syntax a key may sit inside while still being added to a registry mapping.
_REGISTRY_CONTAINERS = (*_STRING_BUILDERS, ast.Dict, ast.keyword)
#: Source text that spells an import of the retired root.
_ROOT_IMPORT_TEXT = re.compile(rf"\b(?:import|from)\s+{LEGACY_ROOT}\b")


@dataclass(frozen=True)
class Usage:
    """One place the retired namespace is named, and how it is named there."""

    path: str
    line: int
    kind: str
    text: str

    def as_dict(self) -> dict[str, object]:
        """Return the usage as plain data for the JSON report."""
        return {
            "path": self.path,
            "line": self.line,
            "kind": self.kind,
            "text": self.text,
        }


@dataclass
class Inventory:
    """The classified result of scanning a set of Python files."""

    imports: list[Usage] = field(default_factory=list)
    active_strings: list[Usage] = field(default_factory=list)
    retained_strings: list[Usage] = field(default_factory=list)
    unreviewed_strings: list[Usage] = field(default_factory=list)
    prose: list[Usage] = field(default_factory=list)
    unparsed: list[Usage] = field(default_factory=list)

    @property
    def active(self) -> list[Usage]:
        """Return every usage that would load or register a second identity."""
        return [*self.imports, *self.active_strings]

    def as_dict(self) -> dict[str, object]:
        """Return the whole inventory as plain data for the JSON report."""
        return {
            "active_total": len(self.active),
            "imports": [usage.as_dict() for usage in self.imports],
            "active_strings": [usage.as_dict() for usage in self.active_strings],
            "retained_strings": [usage.as_dict() for usage in self.retained_strings],
            "retained_files": sorted(
                {usage.path for usage in self.retained_strings},
            ),
            "unreviewed_strings": [
                usage.as_dict() for usage in self.unreviewed_strings
            ],
            "prose_total": len(self.prose),
            "prose_files": sorted({usage.path for usage in self.prose}),
            "unparsed": [usage.as_dict() for usage in self.unparsed],
        }


def tracked_python_files(repository: Path = REPOSITORY_ROOT) -> tuple[Path, ...]:
    """Return the repository's tracked Python files, in a stable order."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    names = (name for name in listed.stdout.decode("utf-8").split("\0") if name)
    return tuple(sorted(repository / name for name in names))


def _names_a_legacy_module(name: str | None) -> bool:
    """Report whether a dotted name is the retired namespace or inside it."""
    if not name:
        return False
    return name == LEGACY_NAMESPACE or name.startswith(f"{LEGACY_NAMESPACE}.")


def _names_the_legacy_root(name: str | None) -> bool:
    """Report whether a dotted name loads the retired package root at all."""
    if not name:
        return False
    return name == LEGACY_ROOT or name.startswith(f"{LEGACY_ROOT}.")


def _import_usages(tree: ast.AST, relative: str) -> Iterator[Usage]:
    """Yield import statements that load the package under the retired name."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _names_the_legacy_root(alias.name):
                    yield Usage(relative, node.lineno, "import", f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if _names_the_legacy_root(node.module):
                names = ", ".join(alias.name for alias in node.names)
                yield Usage(
                    relative,
                    node.lineno,
                    "import",
                    f"from {node.module} import {names}",
                )


def _callee_tail(func: ast.expr) -> str | None:
    """Return the last name of a callee, however it is reached."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _dotted(node: ast.expr) -> str | None:
    """Return the dotted source name of an attribute chain, when it is one."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _is_module_registry(node: ast.expr) -> bool:
    """Report whether an expression spells some module's `modules` attribute."""
    name = _dotted(node)
    return name is not None and "." in name and name.rsplit(".", 1)[1] == "modules"


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    """Map every node's identity to its parent node."""
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _enclosing_call(
    node: ast.AST,
    parents: dict[int, ast.AST],
    containers: tuple[type[ast.AST], ...],
) -> ast.Call | None:
    """Return the call a node is an argument of, looking through `containers`."""
    current = node
    parent = parents.get(id(current))
    while isinstance(parent, containers):
        current = parent
        parent = parents.get(id(current))
    if isinstance(parent, ast.Call) and current is not parent.func:
        return parent
    return None


def _registry_context(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    """Report whether a string is a key being added to a module registry."""
    parent = parents.get(id(node))
    if (
        isinstance(parent, ast.Subscript)
        and parent.slice is node
        and isinstance(parent.ctx, ast.Store)
        and _is_module_registry(parent.value)
    ):
        return True
    call = _enclosing_call(node, parents, _REGISTRY_CONTAINERS)
    if call is None:
        return False
    tail = _callee_tail(call.func)
    if (
        isinstance(call.func, ast.Attribute)
        and tail in REGISTRY_METHODS
        and _is_module_registry(call.func.value)
    ):
        return True
    return (
        tail in REGISTRY_CALLEES
        and bool(call.args)
        and _is_module_registry(call.args[0])
    )


def _dynamic_import_context(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    """Report whether a string is the name a call imports.

    Only a direct argument counts, or a piece of one built by concatenation, so
    a collection of names passed as data is not mistaken for an import target.
    """
    call = _enclosing_call(node, parents, (*_STRING_BUILDERS, ast.keyword))
    if call is None:
        return False
    tail = _callee_tail(call.func)
    dotted_target = node.value.startswith(f"{LEGACY_ROOT}.")
    if tail in MODULE_NAME_CALLEES:
        return True
    if tail in TARGET_PATH_CALLEES:
        return dotted_target
    patch_callee = "patch" in (_dotted(call.func) or "").split(".")
    return tail in REGISTRY_CALLEES and patch_callee and dotted_target


def _assigned_strings(tree: ast.AST) -> dict[str, list[ast.Constant]]:
    """Map each name to the string constants assigned to it anywhere in a file."""
    assigned: dict[str, list[ast.Constant]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [
                target for target in node.targets if isinstance(target, ast.Name)
            ]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        else:
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for target in targets:
                assigned.setdefault(target.id, []).append(value)
    return assigned


def _unwrap_source(node: ast.expr) -> ast.expr:
    """Look through a single-argument wrapper such as `textwrap.dedent(SOURCE)`."""
    while isinstance(node, ast.Call) and len(node.args) == 1 and not node.keywords:
        node = node.args[0]
    return node


def _executed_nodes(
    tree: ast.AST,
    assigned: dict[str, list[ast.Constant]],
) -> Iterator[ast.expr]:
    """Yield every string expression the code executes as Python source."""
    positions: list[ast.expr] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and _callee_tail(node.func) in SOURCE_EXECUTORS
            and node.args
        ):
            positions.append(node.args[0])
        elif isinstance(node, (ast.List, ast.Tuple)):
            for flag, source in pairwise(node.elts):
                if isinstance(flag, ast.Constant) and flag.value == "-c":
                    positions.append(source)
    for position in positions:
        source = _unwrap_source(position)
        if isinstance(source, ast.Name):
            yield from assigned.get(source.id, [])
        elif isinstance(source, (ast.Constant, ast.JoinedStr)):
            yield source


def _source_text(node: ast.expr) -> str | None:
    """Return the Python text a string expression holds, placeholders included."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        pieces = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                pieces.append(value.value)
            else:
                pieces.append("_placeholder")
        return "".join(pieces)
    return None


def _source_is_active(text: str) -> bool:
    """Report whether executed source text loads or registers a second identity.

    Text that names the retired namespace or spells an import of its root but
    cannot be parsed is unknown, so it counts as active.
    """
    if LEGACY_NAMESPACE not in text and not _ROOT_IMPORT_TEXT.search(text):
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return True
    return bool(_active_findings(tree, "<executed-source>"))


def _active_findings(tree: ast.AST, relative: str) -> list[tuple[Usage, set[int]]]:
    """Return every active reference in a tree with the string nodes it covers."""
    findings: list[tuple[Usage, set[int]]] = [
        (usage, set()) for usage in _import_usages(tree, relative)
    ]
    parents = _parents(tree)
    covered: set[int] = set()
    for node in _executed_nodes(tree, _assigned_strings(tree)):
        text = _source_text(node)
        if text is None or id(node) in covered or not _source_is_active(text):
            continue
        nodes = {id(node), *(id(child) for child in ast.walk(node))}
        covered.update(nodes)
        usage = Usage(relative, node.lineno, "executed-source", _excerpt(text))
        findings.append((usage, nodes))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in covered or not _names_the_legacy_root(node.value):
            continue
        if _registry_context(node, parents):
            kind = "module-registry"
        elif _dynamic_import_context(node, parents):
            kind = "dynamic-import"
        else:
            continue
        usage = Usage(relative, node.lineno, kind, _excerpt(node.value))
        findings.append((usage, {id(node)}))
    return findings


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Return the identities of every docstring constant in the tree.

    A docstring is prose about the code, not a value the code uses, so it is
    reported like a comment rather than as a mention.
    """
    documented = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    identities: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, documented):
            continue
        body = getattr(node, "body", [])
        if not body or not isinstance(body[0], ast.Expr):
            continue
        first = body[0].value
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            identities.add(id(first))
    return identities


def _mentions(tree: ast.AST, excluded: set[int]) -> Iterator[ast.Constant]:
    """Yield string constants mentioning the retired namespace, minus exclusions."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and LEGACY_NAMESPACE in node.value
            and id(node) not in excluded
        ):
            yield node


def _prose_usages(
    source: str, relative: str, string_lines: set[int]
) -> Iterable[Usage]:
    """Yield comment lines that mention the retired namespace."""
    for number, line in enumerate(source.splitlines(), start=1):
        if LEGACY_NAMESPACE not in line or number in string_lines:
            continue
        if "#" in line and LEGACY_NAMESPACE in line.split("#", 1)[1]:
            yield Usage(relative, number, "comment", line.strip()[:120])


def _excerpt(value: str) -> str:
    """Return a single-line, bounded excerpt of a string constant."""
    collapsed = " ".join(value.split())
    return collapsed if len(collapsed) <= 120 else f"{collapsed[:117]}..."


def scan(paths: Sequence[Path], repository: Path = REPOSITORY_ROOT) -> Inventory:
    """Classify every mention of the retired namespace in the given files."""
    inventory = Inventory()
    for path in paths:
        relative = path.relative_to(repository).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as error:
            inventory.unparsed.append(Usage(relative, 0, "unreadable", str(error)))
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as error:
            inventory.unparsed.append(
                Usage(relative, error.lineno or 0, "syntax-error", str(error.msg))
            )
            continue

        docstrings = _docstring_nodes(tree)
        string_lines: set[int] = set()
        excluded = set(docstrings)
        for usage, nodes in _active_findings(tree, relative):
            if usage.kind == "import":
                inventory.imports.append(usage)
            else:
                inventory.active_strings.append(usage)
                string_lines.add(usage.line)
                excluded.update(nodes)

        retained = relative in RETAINED_STRING_REFERENCES
        for node in _mentions(tree, excluded):
            string_lines.add(node.lineno)
            usage = Usage(relative, node.lineno, "string", _excerpt(node.value))
            if retained:
                inventory.retained_strings.append(usage)
            else:
                inventory.unreviewed_strings.append(usage)

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and id(node) in docstrings
                and LEGACY_NAMESPACE in node.value
            ):
                string_lines.add(node.lineno)
                inventory.prose.append(
                    Usage(relative, node.lineno, "docstring", _excerpt(node.value))
                )
        inventory.prose.extend(_prose_usages(source, relative, string_lines))
    return inventory


def exit_status(inventory: Inventory) -> int:
    """Return the command's exit status for a classified inventory."""
    if inventory.unparsed:
        return 2
    return 1 if inventory.active or inventory.unreviewed_strings else 0


def _render(inventory: Inventory) -> str:
    """Describe the inventory for a human reading the delivery record."""
    lines = [
        f"Active legacy imports:          {len(inventory.imports)}",
        f"Active legacy string references: {len(inventory.active_strings)}",
        f"Retained inert mentions:        {len(inventory.retained_strings)} "
        f"in {len({usage.path for usage in inventory.retained_strings})} file(s)",
        f"Unreviewed inert mentions:      {len(inventory.unreviewed_strings)}",
        f"Prose mentions (never active):  {len(inventory.prose)}",
    ]
    for usage in inventory.active:
        lines.append(f"  ACTIVE {usage.kind} {usage.path}:{usage.line}: {usage.text}")
    for usage in inventory.unreviewed_strings:
        lines.append(f"  UNREVIEWED {usage.path}:{usage.line}: {usage.text}")
    for usage in inventory.unparsed:
        lines.append(f"  UNPARSED {usage.path}:{usage.line}: {usage.text}")
    return "\n".join(lines)


def main(arguments: Sequence[str] | None = None) -> int:
    """Scan the repository and fail when any active or unreviewed use remains."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full inventory as JSON instead of a summary.",
    )
    parsed = parser.parse_args(arguments)

    inventory = scan(tracked_python_files())
    if parsed.json:
        print(json.dumps(inventory.as_dict(), indent=2, sort_keys=True))
    else:
        print(_render(inventory))
    return exit_status(inventory)


if __name__ == "__main__":
    raise SystemExit(main())
