"""AST contracts for the extracted slice, with adversarial checker controls."""
from __future__ import annotations

import ast
from importlib.util import resolve_name
from itertools import permutations
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = "packet_tracer_mcp.application.cp_scale_live"
CLI = "packet_tracer_mcp.adapters.cli.cp_scale_live"
FACADE = "tools.cp_scale_canonical_live"


def _qualified(node: ast.AST, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return _qualified(node.value, aliases) + "." + node.attr
    return ""


def _import_facts(module: str, tree: ast.AST, sources: dict[str, str]):
    aliases = {}
    targets = {}
    package = module if any(name.startswith(module + ".") for name in sources) else module.rsplit(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets[node] = tuple(item.name for item in node.names)
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module or ""
            targets[node] = (base, *(base + "." + item.name for item in node.names))
            aliases.update((item.asname or item.name, base + "." + item.name) for item in node.names)
    return aliases, targets


def _runtime_nodes(node: ast.AST, aliases: dict[str, str]):
    yield node
    if isinstance(node, ast.If) and _qualified(node.test, aliases) == "typing.TYPE_CHECKING":
        for item in node.orelse:
            yield from _runtime_nodes(item, aliases)
        return
    for child in ast.iter_child_nodes(node):
        yield from _runtime_nodes(child, aliases)


def _component(module: str) -> bool:
    return module == APP or module.startswith(APP + ".") or module == CLI or any(module.startswith(
        "packet_tracer_mcp.infrastructure." + layer + ".cp_scale")
        for layer in ("observation", "diagnostics", "persistence", "execution"))


def _cycles(graph: dict[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    """Tarjan on the entire graph; only then select SCCs containing CP.

    Report an actual closed path through a CP member, not a sorted SCC that
    could misleadingly imply edges between unrelated neighbours.
    """
    indices = {}
    lowlinks = {}
    stack = []
    on_stack = set()
    components = []
    def visit(module):
        indices[module] = lowlinks[module] = len(indices)
        stack.append(module)
        on_stack.add(module)
        for dependency in sorted(graph.get(module, ())):
            if dependency not in indices:
                visit(dependency)
                lowlinks[module] = min(lowlinks[module], lowlinks[dependency])
            elif dependency in on_stack:
                lowlinks[module] = min(lowlinks[module], indices[dependency])
        if lowlinks[module] == indices[module]:
            component = set()
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.add(member)
                if member == module:
                    break
            components.append(component)
    for module in sorted(graph):
        if module not in indices:
            visit(module)

    cycles = []
    for component in components:
        cp_members = sorted(member for member in component if _component(member))
        if not cp_members or (len(component) == 1 and cp_members[0] not in graph.get(cp_members[0], ())):
            continue
        start = cp_members[0]
        searched = {start}
        def path_back(module, path):
            for neighbour in sorted(graph.get(module, ())):
                if neighbour == start:
                    return (*path, start)
                if neighbour in component and neighbour not in searched:
                    searched.add(neighbour)
                    found = path_back(neighbour, (*path, neighbour))
                    if found:
                        return found
            return ()
        cycles.append(path_back(start, (start,)))
    return tuple(cycles)


def _static_facade(tree: ast.Module, aliases: dict[str, str]) -> bool:
    guard = ast.parse('if __name__ == "__main__":\n    raise SystemExit(main())').body[0]
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.ImportFrom) and node.module in {"__future__", CLI}:
            continue
        if (isinstance(node, ast.If) and ast.dump(node) == ast.dump(guard)
            and aliases.get("main") == CLI + ".main"):
            continue
        return False
    return True


def _boundary_issues(sources: dict[str, str]) -> tuple[tuple[str, ...], ...]:
    issues = []
    graph = {}
    for module, source in sources.items():
        tree = ast.parse(source, filename=module)
        aliases, targets = _import_facts(module, tree, sources)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _qualified(node.func, aliases) in {"importlib.import_module", "__import__"}:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    targets[node] = (node.args[0].value,)
        for dependencies in targets.values():
            for target in dependencies:
                if module != FACADE and (target == "tools" or target.startswith("tools.")):
                    issues.append(("src_to_tools", module, target))
                if ((module == APP or module.startswith(APP + "."))
                    and (target == "packet_tracer_mcp.infrastructure" or target.startswith("packet_tracer_mcp.infrastructure."))):
                    issues.append(("concrete_in_application", module, target))
        edges = []
        for node in _runtime_nodes(tree, aliases):
            for target in targets.get(node, ()):
                parts = target.split(".")
                while parts and ".".join(parts) not in sources:
                    parts.pop()
                if parts and ".".join(parts) != module:
                    edges.append(".".join(parts))
        graph[module] = tuple(dict.fromkeys(edges))
        if module == FACADE and not _static_facade(tree, aliases):
            issues.append(("facade_implementation", module))
    return (tuple(issues) + tuple(("runtime_cycle", *cycle) for cycle in _cycles(graph))
        + _private_relay_issues(sources))


def _private_relay_issues(sources: dict[str, str]) -> tuple[tuple[str, ...], ...]:
    relays: dict[tuple[str, str], str] = {}
    imports: list[tuple[str, str, str]] = []
    for module, source in sources.items():
        tree = ast.parse(source, filename=module)
        _, targets = _import_facts(module, tree, sources)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            base = targets[node][0]
            for item in node.names:
                local = item.asname or item.name
                imports.append((module, base, item.name))
                if item.asname and local.startswith("_") and not item.name.startswith("_"):
                    relays[(module, local)] = base + "." + item.name
    return tuple(
        ("private_relay", consumer, relay, name, relays[(relay, name)])
        for consumer, relay, name in imports
        if consumer != relay and (relay, name) in relays
    )


_LEXICAL_SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _scope_nodes(scope: ast.AST) -> tuple[ast.AST, ...]:
    """Include child scope declarations, but never their bindings or bodies."""
    nodes = []
    def visit(node):
        nodes.append(node)
        if node is not scope and isinstance(node, _LEXICAL_SCOPES):
            return
        for child in ast.iter_child_nodes(node):
            visit(child)
    visit(scope)
    return tuple(nodes)


def _scope_import_aliases(module, nodes, sources):
    imports = ast.Module(body=[node for node in nodes if isinstance(node, (ast.Import, ast.ImportFrom))], type_ignores=[])
    return _import_facts(module, imports, sources)[0]


def _state_issues(sources: dict[str, str]) -> tuple[tuple[str, ...], ...]:
    parsed = {module: ast.parse(source, filename=module) for module, source in sources.items()}
    class_index = {module + "." + node.name: (module, node) for module, tree in parsed.items()
                   for node in tree.body if isinstance(node, ast.ClassDef)}
    module_aliases = {module: _scope_import_aliases(module, _scope_nodes(tree), sources)
                      for module, tree in parsed.items()}
    def reference(node, module):
        name = _qualified(node, module_aliases[module])
        return module + "." + name if module + "." + name in class_index else name
    def value_class(name, visited=()):
        if name in {"pydantic.BaseModel", "enum.Enum", "enum.IntEnum", "enum.StrEnum"}:
            return True
        if name not in class_index or name in visited:
            return False
        module, definition = class_index[name]
        if any(reference(item.func if isinstance(item, ast.Call) else item, module) == "dataclasses.dataclass"
               for item in definition.decorator_list):
            return True
        return any(value_class(reference(base, module), (*visited, name)) for base in definition.bases)
    def service_references(name, visited=()):
        if name in visited:
            return ()
        if name in {"typing.Callable", "collections.abc.Callable"}:
            return (name,)
        if name not in class_index:
            return ()
        if not value_class(name):
            return (name,)
        module, definition = class_index[name]
        found = []
        for field in definition.body:
            if isinstance(field, ast.AnnAssign):
                for item in ast.walk(field.annotation):
                    if isinstance(item, (ast.Name, ast.Attribute)):
                        found.extend(service_references(reference(item, module), (*visited, name)))
        return tuple(found)
    records = set()
    ledgers = set()
    issues = []
    for module, tree in parsed.items():
        aliases = module_aliases[module]
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not (module == APP + ".run_state"
                or module == APP + ".run_contracts" and node.name == "CPScaleRunReport"):
                continue
            name = module + "." + node.name
            records.add(name)
            for service in service_references(name):
                issues.append(("state_service", name, service))
            if module.endswith(".run_state"):
                ledgers.add(name)
            if not any(isinstance(item, ast.Call) and _qualified(item.func, aliases) == "dataclasses.dataclass"
                and any(keyword.arg == "frozen" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
                        for keyword in item.keywords) for item in node.decorator_list):
                issues.append(("mutable_state", name))
            for field in node.body:
                if isinstance(field, ast.AnnAssign):
                    annotations = {_qualified(item, aliases) for item in ast.walk(field.annotation)}
                    if annotations & {"object", "dict", "typing.Dict", "typing.Any", "typing.Callable", "collections.abc.Callable"}:
                        issues.append(("open_state", name, field.target.id))

    def root_name(node):
        while isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        return node.id if isinstance(node, ast.Name) else ""

    def inspect_scope(module, scope, inherited_aliases, inherited_variables):
        nodes = _scope_nodes(scope)
        local_imports = _scope_import_aliases(module, nodes, sources)
        local_names = {node.id for node in nodes if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
        local_names.update(node.arg for node in nodes if isinstance(node, ast.arg))
        local_names.update(node.name for node in nodes if node is not scope and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
        local_names.update(local_imports)
        local_names.difference_update(name for node in nodes if isinstance(node, (ast.Global, ast.Nonlocal)) for name in node.names)
        aliases = {name: value for name, value in inherited_aliases.items() if name not in local_names}
        aliases.update(local_imports)
        aliases.update({node.name: module + "." + node.name for node in nodes
                        if isinstance(node, ast.ClassDef) and module + "." + node.name in records})
        variables = {name: set(kinds) for name, kinds in inherited_variables.items() if name not in local_names}
        for node in nodes:
            if isinstance(node, ast.arg):
                name, annotation = node.arg, node.annotation
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name, annotation = node.target.id, node.annotation
            else:
                continue
            if annotation is not None:
                kinds = {_qualified(item, aliases) for item in ast.walk(annotation)} & records
                if kinds:
                    variables.setdefault(name, set()).update(kinds)

        # Finite powerset lattice: bindings only gain record types. Conflicting
        # assignments remain conservative facts, never First -> Second -> First.
        changed = True
        while changed:
            changed = False
            for node in nodes:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                    continue
                value = node.value
                kinds = variables.get(value.id, set()) if isinstance(value, ast.Name) else set()
                if isinstance(value, ast.Call):
                    called = _qualified(value.func, aliases)
                    kinds = ({called} if called in records else variables.get(root_name(value.args[0]), set())
                             if called == "dataclasses.replace" and value.args else set())
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                for target in targets:
                    if isinstance(target, ast.Name) and kinds:
                        known = variables.setdefault(target.id, set())
                        added = kinds - known
                        if added:
                            known.update(added)
                            changed = True
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
                targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else (node.target,)
                if any(not isinstance(target, ast.Name) and root_name(target) in variables for target in targets):
                    issues.append(("state_mutation", module, str(node.lineno)))
            if isinstance(node, ast.Call):
                called = _qualified(node.func, aliases)
                replaced = (variables.get(root_name(node.args[0]), set()) if called == "dataclasses.replace" and node.args else set())
                if module != APP + ".coordinator" and (called in ledgers or replaced & ledgers):
                    issues.append(("external_state_owner", module, str(node.lineno)))
                if ((called in {"setattr", "delattr", "object.__setattr__"} and node.args and root_name(node.args[0]) in variables)
                    or isinstance(node.func, ast.Attribute) and node.func.attr in {"append", "extend", "update", "clear", "pop", "remove", "insert"}
                    and root_name(node.func.value) in variables):
                    issues.append(("state_mutation", module, str(node.lineno)))
        for child in nodes:
            if child is not scope and isinstance(child, _LEXICAL_SCOPES):
                # A method's lexical parent skips its class namespace; nested
                # functions retain the containing function's bindings.
                parent_aliases, parent_variables = ((inherited_aliases, inherited_variables)
                    if isinstance(scope, ast.ClassDef) else (aliases, variables))
                inspect_scope(module, child, parent_aliases, parent_variables)

    for module, tree in parsed.items():
        inspect_scope(module, tree, {}, {})
    return tuple(issues)


@pytest.mark.parametrize("sources,code", [
    ({APP + ".coordinator": "from tools import cp_scale_canonical_live as old"}, "src_to_tools"),
    ({"packet_tracer_mcp.domain.example": "import tools.cp_scale_canonical_live"}, "src_to_tools"),
    ({"packet_tracer_mcp": "import tools.cp_scale_canonical_live"}, "src_to_tools"),
    ({"src": "from tools import cp_scale_canonical_live"}, "src_to_tools"),
    ({APP + ".coordinator": "from importlib import import_module as load\nload('tools.cp_scale_canonical_live')"}, "src_to_tools"),
    ({APP + ".coordinator": "from ...infrastructure.observation.cp_scale_live import observer"}, "concrete_in_application"),
    ({APP: "import packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime"}, "concrete_in_application"),
    ({APP + ".coordinator": "from packet_tracer_mcp import infrastructure"}, "concrete_in_application"),
    ({APP + ".coordinator": "from .stage_executor import execute\n", APP + ".stage_executor": "from ...infrastructure.diagnostics.cp_scale_live import diagnose\n",
      "packet_tracer_mcp.infrastructure.diagnostics.cp_scale_live": "from ...application.cp_scale_live.coordinator import run"}, "runtime_cycle"),
    ({FACADE: "def run():\n    return 0"}, "facade_implementation"),
    ({FACADE: "class Execution: pass"}, "facade_implementation"),
    ({FACADE: "from importlib import import_module as load\nimplementation = load('example')"}, "facade_implementation"),
    ({FACADE: "from packet_tracer_mcp.adapters.cli.cp_scale_live import run\nglobals().update(vars(run))"}, "facade_implementation"),
    ({FACADE: "from packet_tracer_mcp.adapters.cli.cp_scale_live import main\nif __name__ == '__main__':\n    for stage in ('one', 'two'):\n        main()"}, "facade_implementation"),
])
def test_import_and_facade_checker_rejects_actual_violations(sources, code):
    assert code in [issue[0] for issue in _boundary_issues(sources)]


def test_import_checker_ignores_docstrings_and_type_only_cycles():
    sources = {
        APP + ".coordinator": '"""import tools; for stage in workflow: dispatch()"""\nfrom typing import TYPE_CHECKING as checking\nif checking:\n    from .stage_executor import Result\n',
        APP + ".stage_executor": "from .coordinator import Result\n",
        FACADE: '"""def run(): use globals()"""\nfrom packet_tracer_mcp.adapters.cli.cp_scale_live import main, run\nif __name__ == "__main__":\n    raise SystemExit(main())\n',
    }
    assert _boundary_issues(sources) == ()


def test_import_checker_rejects_private_owner_relay():
    sources = {
        APP + ".owner": "def decide(): return True",
        "packet_tracer_mcp.infrastructure.observation.relay":
            "from ...application.cp_scale_live.owner import decide as _decide",
        "packet_tracer_mcp.infrastructure.observation.consumer":
            "from .relay import _decide",
    }

    assert [item[0] for item in _boundary_issues(sources)] == ["private_relay"]


@pytest.mark.parametrize("order", tuple(permutations(("first", "second", "coordinator"))))
@pytest.mark.parametrize("reverse_edges", [False, True])
def test_runtime_cycle_through_external_scc_is_independent_of_visit_order(order, reverse_edges):
    first = "packet_tracer_mcp.application.use_cases.first"
    second = "packet_tracer_mcp.application.use_cases.second"
    coordinator = APP + ".coordinator"
    names = {"first": first, "second": second, "coordinator": coordinator}
    edges = {first: (second, coordinator), second: (first,), coordinator: (second,)}
    sources = {names[name]: "\n".join("import " + target for target in (
        reversed(edges[names[name]]) if reverse_edges else edges[names[name]])) for name in order}
    cycles = [issue[1:] for issue in _boundary_issues(sources) if issue[0] == "runtime_cycle"]
    assert len(cycles) == 1
    cycle = cycles[0]
    assert coordinator in cycle
    assert cycle[0] == cycle[-1]
    assert len(cycle) == 4
    assert all(target in edges[source] for source, target in zip(cycle, cycle[1:]))


@pytest.mark.parametrize("definition,consumer,code", [
    ("@dataclass\nclass Ledger:\n    count: int = 0", "", "mutable_state"),
    ("@dataclass(frozen=True)\nclass Ledger:\n    data: dict[str, object]", "", "open_state"),
    ("@dataclass(frozen=True)\nclass Ledger:\n    effect: Callable[[], None]", "", "open_state"),
    ("@dataclass(frozen=True)\nclass Ledger:\n    runtime: Any", "", "open_state"),
    ("@dataclass(frozen=True)\nclass Ledger:\n    count: int = 0", "value = Ledger()", "external_state_owner"),
    ("@dataclass(frozen=True)\nclass Ledger:\n    count: int = 0", "def publish(value: Ledger):\n    alias = value\n    alias.count = 3", "state_mutation"),
    ("@dataclass(frozen=True)\nclass Ledger:\n    count: int = 0", "def publish(value: Ledger):\n    setattr(value, 'count', 3)", "state_mutation"),
    ("@dataclass(frozen=True)\nclass Ledger:\n    entries: tuple[str, ...] = ()", "def publish(value: Ledger):\n    value.entries.append('extra')", "state_mutation"),
    ("@dataclass(frozen=True)\nclass Ledger:\n    count: int = 0", "def publish(value: Ledger):\n    return replace(value, count=3)", "external_state_owner"),
])
def test_state_checker_rejects_mutation_and_multiple_owners(definition, consumer, code):
    sources = {
        APP + ".run_state": "from dataclasses import dataclass\nfrom typing import Any, Callable\n" + definition,
        APP + ".backend": "from .run_state import Ledger\nfrom dataclasses import replace\n" + consumer,
    }
    assert code in [issue[0] for issue in _state_issues(sources)]


@pytest.mark.parametrize("operation,expected", [
    ("object.__setattr__(value, 'count', 3)", "state_mutation"),
    ("replace(value, count=4)", "external_state_owner"),
])
def test_local_state_annotation_rejects_effect_with_opaque_initializer(operation, expected):
    sources = {
        APP + ".run_state": "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass Ledger:\n    count: int = 0",
        APP + ".backend": "from .run_state import Ledger\nfrom dataclasses import replace\n"
            "def publish():\n    value: Ledger = get_state()\n    " + operation,
    }
    assert [issue[0] for issue in _state_issues(sources)] == [expected]


def test_state_inference_terminates_with_reused_local_names_in_separate_functions():
    # The old fixed point oscillated forever. A subprocess bounds this causal
    # regression even if that implementation is accidentally restored.
    program = """
from tests.test_cp_scale_live_architecture import APP, _state_issues
sources = {
    APP + '.run_state': 'from dataclasses import dataclass\\n@dataclass(frozen=True)\\nclass First:\\n    count: int = 0\\n@dataclass(frozen=True)\\nclass Second:\\n    count: int = 0',
    APP + '.coordinator': 'from .run_state import First, Second\\ndef first():\\n    value = First()\\n    return value\\ndef second():\\n    value = Second()\\n    return value',
}
assert _state_issues(sources) == ()
print('scope-check-complete')
"""
    try:
        result = subprocess.run([sys.executable, "-c", program], cwd=ROOT,
            capture_output=True, text=True, timeout=5, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail("state inference failed to reach a bounded fixed point for independent lexical scopes")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "scope-check-complete"


def test_state_bindings_do_not_leak_between_sibling_functions_and_methods():
    sources = {
        APP + ".run_state": "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass Ledger:\n    count: int = 0",
        APP + ".backend": "from .run_state import Ledger\n"
            "def inspect(value: Ledger):\n    return value.count\n"
            "def publish(value: object):\n    object.__setattr__(value, 'count', 3)\n"
            "class Presentation:\n    def publish(self, value: object):\n        object.__setattr__(value, 'count', 3)",
    }
    assert _state_issues(sources) == ()


@pytest.mark.parametrize("service", ["SessionPort", "Resources", "Backend"])
def test_state_checker_rejects_direct_or_bundled_services(service):
    sources = {
        APP + ".session": "from dataclasses import dataclass\nfrom typing import Protocol\n"
            "class SessionPort(Protocol):\n    def close(self) -> None: ...\n"
            "@dataclass(frozen=True)\nclass Resources:\n    session: SessionPort\n"
            "class Backend:\n    def acquire(self): pass\n",
        APP + ".run_state": "from dataclasses import dataclass\nfrom .session import " + service + "\n"
            "@dataclass(frozen=True)\nclass Ledger:\n    value: " + service + "\n",
    }
    assert "state_service" in [issue[0] for issue in _state_issues(sources)]


def _production_sources() -> dict[str, str]:
    sources = {}
    for path in (ROOT / "src").rglob("*.py"):
        parts = list(path.relative_to(ROOT / "src").with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        sources[".".join(parts) or "src"] = path.read_text(encoding="utf-8")
    sources[FACADE] = (ROOT / "tools/cp_scale_canonical_live.py").read_text(encoding="utf-8")
    return sources


def test_production_dependency_graph_and_static_facade():
    assert _boundary_issues(_production_sources()) == ()


def test_run_snapshots_are_closed_frozen_and_only_coordinator_replaces_them():
    assert _state_issues(_production_sources()) == ()


def test_cli_and_tool_publish_no_temporary_private_compatibility_surface():
    adapter = ast.parse((ROOT / "src/packet_tracer_mcp/adapters/cli/cp_scale_live.py").read_text(encoding="utf-8"))
    facade = ast.parse((ROOT / "tools/cp_scale_canonical_live.py").read_text(encoding="utf-8"))
    retired = {
        "GOVERNED_ROOT", "EVIDENCE_PATH", "CHECKPOINT_PATH", "FINAL_CHECKPOINT_PATH",
        "CANONICAL_EVIDENCE_DIR", "CPScaleStageAdapterResult", "_BUILD_STAGES",
        "_execute_stage", "_stage_voice",
        "_write_evidence", "_write_checkpoint_summary", "_wait_for_site_forwarding",
        "_wait_for_core_forwarding", "_network_state_observation",
        "_post_failure_simulation_diagnostic", "_frame_observer_discovery",
    }
    adapter_definitions = {
        node.name for node in adapter.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    } | {
        target.id for node in adapter.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
    } | {
        item.asname or item.name
        for node in adapter.body if isinstance(node, (ast.Import, ast.ImportFrom))
        for item in node.names
    }
    facade_imports = {
        item.name for node in facade.body if isinstance(node, ast.ImportFrom)
        and node.module == CLI for item in node.names
    }

    assert adapter_definitions.isdisjoint(retired)
    assert facade_imports == {"main", "run"}
