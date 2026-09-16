"""Inventory every use of the retired `src.packet_tracer_mcp` import namespace.

The migration's acceptance criterion is not "the text disappeared": a handful of
places must keep naming the retired namespace, because their job is to reject
it. What must be zero is *active* use -- anything that would actually load the
package under a second name.

The two kinds are separated by parsing, not by grepping, because a name written
inside a string literal and a name written as an import mean different things:

`import` statements
    Always active, and allowed nowhere. An `import src.packet_tracer_mcp` in a
    collected module creates the second identity in the process that runs it.

string constants
    Active when something imports them -- `importlib.import_module`,
    `find_spec`, `__import__`, a `monkeypatch.setattr` target -- and inert when
    they are the subject of an assertion, a guard's list of forbidden names, or
    source for a child process that is meant to reproduce the defect. These are
    allowed only in the files listed in `RETAINED_STRING_REFERENCES`, each with
    the reason it is retained.

Comments and docstrings are reported separately and never fail the inventory;
prose about the migration is not a use of it.

Exit status: 0 when no active use remains outside the retained set, 1 when any
does, and 2 when a file could not be parsed, which is unresolved and therefore
a failure rather than an empty answer.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

#: The retired import namespace this inventory looks for.
LEGACY_NAMESPACE = "src.packet_tracer_mcp"
#: Its package root, which is equally unusable as an import name.
LEGACY_ROOT = "src"

#: Files allowed to keep the retired name inside a string constant, and why.
#: Every entry names a place whose purpose is to refuse or reproduce the retired
#: identity. Adding one is a decision: it must not be a way to park a real use.
RETAINED_STRING_REFERENCES: dict[str, str] = {
    "scripts/namespace_inventory.py": (
        "This inventory declares the name it searches for."
    ),
    "scripts/reproduce_namespace_identity.py": (
        "The preserved pre-migration reproduction; it loads both names on "
        "purpose, in a child process, to keep the defect demonstrable."
    ),
    "src/packet_tracer_mcp/infrastructure/execution/import_isolation_preflight.py": (
        "The LIVE gate names the retired namespace to reject it."
    ),
    "tests/namespace_preflight.py": (
        "The suite's fail-closed gate names the retired namespace to reject it."
    ),
    "tests/test_namespace_preflight.py": (
        "Proves the gate refuses the retired namespace."
    ),
    "tests/test_namespace_inventory.py": (
        "Proves this inventory reacts to an active use."
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
    "tests/test_worktree_isolation.py": (
        "The worktree identity guard names the retired namespace to forbid it."
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
    prose: list[Usage] = field(default_factory=list)
    unparsed: list[Usage] = field(default_factory=list)

    @property
    def active(self) -> list[Usage]:
        """Return every usage that would load the package under a second name."""
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


def _import_usages(tree: ast.AST, relative: str) -> Iterable[Usage]:
    """Yield import statements that load the package under the retired name."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _names_a_legacy_module(alias.name) or alias.name == LEGACY_ROOT:
                    yield Usage(relative, node.lineno, "import", f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if _names_a_legacy_module(node.module):
                yield Usage(
                    relative, node.lineno, "import", f"from {node.module} import ..."
                )


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Return the identities of every docstring constant in the tree.

    A docstring is prose about the code, not a value the code uses, so it is
    reported like a comment rather than as a dynamic import target.
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


def _string_usages(
    tree: ast.AST, relative: str, docstrings: set[int]
) -> Iterable[Usage]:
    """Yield non-docstring string constants that contain the retired namespace."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if LEGACY_NAMESPACE in node.value and id(node) not in docstrings:
                yield Usage(
                    relative,
                    node.lineno,
                    "string",
                    _excerpt(node.value),
                )


def _docstring_prose(
    tree: ast.AST, relative: str, docstrings: set[int]
) -> Iterable[Usage]:
    """Yield docstrings that mention the retired namespace as prose."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) in docstrings
            and LEGACY_NAMESPACE in node.value
        ):
            yield Usage(relative, node.lineno, "docstring", _excerpt(node.value))


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

        inventory.imports.extend(_import_usages(tree, relative))

        docstrings = _docstring_nodes(tree)
        string_lines: set[int] = set()
        retained = relative in RETAINED_STRING_REFERENCES
        for usage in _string_usages(tree, relative, docstrings):
            string_lines.add(usage.line)
            if retained:
                inventory.retained_strings.append(usage)
            else:
                inventory.active_strings.append(usage)

        for usage in _docstring_prose(tree, relative, docstrings):
            string_lines.add(usage.line)
            inventory.prose.append(usage)
        inventory.prose.extend(_prose_usages(source, relative, string_lines))
    return inventory


def _render(inventory: Inventory) -> str:
    """Describe the inventory for a human reading the delivery record."""
    lines = [
        f"Active legacy imports:          {len(inventory.imports)}",
        f"Active legacy string targets:   {len(inventory.active_strings)}",
        f"Retained rejection references:  {len(inventory.retained_strings)} "
        f"in {len({usage.path for usage in inventory.retained_strings})} file(s)",
        f"Prose mentions (never active):  {len(inventory.prose)}",
    ]
    for usage in inventory.active:
        lines.append(f"  ACTIVE {usage.path}:{usage.line}: {usage.text}")
    for usage in inventory.unparsed:
        lines.append(f"  UNPARSED {usage.path}:{usage.line}: {usage.text}")
    return "\n".join(lines)


def main(arguments: Sequence[str] | None = None) -> int:
    """Scan the repository and fail when any active legacy use remains."""
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

    if inventory.unparsed:
        return 2
    return 1 if inventory.active else 0


if __name__ == "__main__":
    raise SystemExit(main())
