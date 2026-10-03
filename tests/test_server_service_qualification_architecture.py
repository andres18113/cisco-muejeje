"""Architecture contracts of the server-service qualification subsystem.

QR03 and QR04 of SERVER-SERVICE-QUALIFICATION-ARCHITECTURE-01: the façade keeps
the public entry and the canonical objects, the package forms the declared
dependency graph, workflows reach neither one another nor the coordinator,
one mutable context exists per invocation, and every executable stage maps to
exactly one explicit handler. The graph checker carries its own negative
controls, so a checker that stopped seeing edges would fail here too.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from importlib.util import resolve_name
from pathlib import Path

import pytest

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    QualificationStage,
    stage_definition,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
PACKAGE = "packet_tracer_mcp.application.server_service_qualification"
FACADE = "packet_tracer_mcp.application.use_cases.qualify_server_services"
WORKFLOWS = PACKAGE + ".workflows"
SUPPORT = tuple(
    f"{PACKAGE}.{name}" for name in ("fixtures", "product_support", "dhcp_observations")
)
FOUNDATION = tuple(
    f"{PACKAGE}.{name}"
    for name in (
        "contracts",
        "operation_budget",
        "ledgered_transport",
        "campaign_authority",
        "record_lifecycle",
    )
)
DOMAIN_PREDICATES = (
    "packet_tracer_mcp.domain.enterprise.services.qualification_product_evidence",
    "packet_tracer_mcp.domain.enterprise.services.qualification_terminal_evidence",
    "packet_tracer_mcp.domain.enterprise.services.sp2_pool_diagnostic",
)

#: Every public top-level name of the starting module (ece5fca), and the two
#: private helpers the SP-2 operator tooling imports from the façade path.
STARTING_PUBLIC_NAMES = frozenset(
    {
        "CampaignQualificationAuthority",
        "D_DHCP_DEFAULT_PURPOSE",
        "DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE",
        "FETCH_OPERATIONS",
        "IsolationObservation",
        "LedgerPhase",
        "LedgeredTransport",
        "MAX_DETAIL",
        "NOT_SELECTED",
        "OperationLedger",
        "OperationRefused",
        "Q3ProductContract",
        "Q3_DEFAULT_PURPOSE",
        "Q3_FL_DEFAULT_PURPOSE",
        "QualificationBoundaries",
        "QualificationCancelled",
        "QualificationResult",
        "RuntimeIdentity",
        "SP1_BINDING_KINDS",
        "SP1_CAPTURE_DEADLINE_SECONDS",
        "SP1_CAPTURE_SAMPLE_CALLS",
        "SP1_REQUIRED_CLIENT_KINDS",
        "SP2_CAPACITY_CONFIGURATION_SHA256",
        "SP2_CAPACITY_MANIFEST_SHA256",
        "SP2_CAPACITY_NORMALIZED_SERVICES_SHA256",
        "SP2_CAPACITY_SERVICE_CAPABILITIES_SHA256",
        "SP2_CAPACITY_TOPOLOGY_SHA256",
        "SP2_MIXED_BUILD",
        "SP2_MIXED_CLIENT_KINDS",
        "SP2_MIXED_CONFIGURATION_SHA256",
        "SP2_MIXED_HELPERS",
        "SP2_MIXED_MANIFEST_SHA256",
        "SP2_MIXED_NORMALIZED_SERVICES_SHA256",
        "SP2_MIXED_PHYSICAL_POOLS",
        "SP2_MIXED_ROUTED_PAIRS",
        "SP2_MIXED_ROUTERS",
        "SP2_MIXED_SERVICE_CAPABILITIES_SHA256",
        "SP2_MIXED_TOPOLOGY_SHA256",
        "SP2_REMOTE_BUILD",
        "SP2_REMOTE_CLIENT",
        "SP2_REMOTE_CONFIGURATION_SHA256",
        "SP2_REMOTE_INTENT_SHA256",
        "SP2_REMOTE_MANIFEST_SHA256",
        "SP2_REMOTE_POOL",
        "SP2_REMOTE_REQUIRED_DEVICE_EVIDENCE",
        "SP2_REMOTE_ROUTERS",
        "SP2_REMOTE_SERVER",
        "SP2_REMOTE_SERVICES_SHA256",
        "SP2_REMOTE_SERVICE_CAPABILITIES_SHA256",
        "SP2_REMOTE_TOPOLOGY_SHA256",
        "SendAndWait",
        "qualify_server_services",
    }
)
OPERATOR_TOOLING_NAMES = {
    "_sp2_capability_digest": ("product_support", "capability_digest"),
    "_sp2_mixed_normalized_services_hash": (
        "workflows.sp2_mixed_product",
        "sp2_mixed_normalized_services_hash",
    ),
}
#: The owner of every re-exported public name.
OWNERS = {
    **dict.fromkeys(
        (
            "MAX_DETAIL",
            "CampaignQualificationAuthority",
            "IsolationObservation",
            "Q3ProductContract",
            "QualificationBoundaries",
            "QualificationCancelled",
            "QualificationResult",
            "RuntimeIdentity",
            "SendAndWait",
        ),
        "contracts",
    ),
    **dict.fromkeys(
        ("LedgerPhase", "OperationLedger", "OperationRefused"), "operation_budget"
    ),
    "LedgeredTransport": "ledgered_transport",
    "NOT_SELECTED": "execution",
    **dict.fromkeys(
        ("D_DHCP_DEFAULT_PURPOSE", "Q3_DEFAULT_PURPOSE", "Q3_FL_DEFAULT_PURPOSE"),
        "dhcp_observations",
    ),
    **dict.fromkeys(
        (
            "DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE",
            "SP1_CAPTURE_DEADLINE_SECONDS",
            "SP1_CAPTURE_SAMPLE_CALLS",
        ),
        "product_support",
    ),
    "FETCH_OPERATIONS": "workflows.https_page",
    **dict.fromkeys(
        ("SP1_BINDING_KINDS", "SP1_REQUIRED_CLIENT_KINDS"),
        "workflows.sp1_routed_product",
    ),
    **{
        name: "workflows.sp2_mixed_product"
        for name in STARTING_PUBLIC_NAMES
        if name.startswith(("SP2_MIXED_", "SP2_CAPACITY_"))
    },
    **{
        name: "workflows.sp2_remote_relay"
        for name in STARTING_PUBLIC_NAMES
        if name.startswith("SP2_REMOTE_")
    },
}
#: The handler the former `if/elif` chain selected for each executable stage.
STARTING_HANDLERS = {
    QualificationStage.Q0: ("workflows.engine", "run_q0"),
    QualificationStage.Q1: ("workflows.https_page", "run_q1"),
    QualificationStage.Q3: ("workflows.original_dhcp", "run_q3"),
    QualificationStage.D_WEB: ("workflows.web_diagnostics", "run_d_web"),
    QualificationStage.D_DHCP: ("workflows.dhcp_diagnostics", "run_d_dhcp"),
    QualificationStage.Q3_FL_C1: ("workflows.fastloop", "run_q3_fastloop"),
    QualificationStage.Q3_FL_C2: ("workflows.fastloop", "run_q3_fastloop"),
    QualificationStage.SP2_NATIVE_POOL: ("workflows.fastloop", "run_q3_fastloop"),
    QualificationStage.Q3_NATIVE_PROBE: (
        "workflows.native_pool",
        "run_q3_native_probe",
    ),
    QualificationStage.Q3_NATIVE_SIZE: ("workflows.native_pool", "run_q3_native_size"),
    QualificationStage.Q3_NATIVE_POLICY: (
        "workflows.native_pool",
        "run_q3_native_policy",
    ),
    QualificationStage.Q3_NATIVE_STABILITY: (
        "workflows.native_pool",
        "run_q3_native_stability",
    ),
    QualificationStage.Q3_NATIVE_SERVE: (
        "workflows.native_pool",
        "run_q3_native_serve",
    ),
    QualificationStage.Q3_NATIVE_PRODUCT: (
        "workflows.native_product",
        "run_q3_native_product",
    ),
    QualificationStage.SP1_ROUTED_W1: (
        "workflows.sp1_routed_product",
        "run_sp1_routed_product",
    ),
    QualificationStage.SP1_ROUTED_W2: (
        "workflows.sp1_routed_product",
        "run_sp1_routed_product",
    ),
    QualificationStage.SP2_REMOTE_RELAY: (
        "workflows.sp2_remote_relay",
        "run_sp2_remote_relay",
    ),
    QualificationStage.SP2_MIXED_PRODUCT: (
        "workflows.sp2_mixed_product",
        "run_sp2_mixed_product",
    ),
    QualificationStage.SP2_CAPACITY_PRODUCT: (
        "workflows.sp2_mixed_product",
        "run_sp2_mixed_product",
    ),
}
#: Stages added after the refactor, each a named delta to the former table
#: rather than a silent widening of it: SP-2's acquisition discriminator
#: (2026-10-02) is the mixed workflow's second driver.
SUCCESSOR_HANDLERS = {
    QualificationStage.SP2_MIXED_ACQUISITION: (
        "workflows.sp2_mixed_product",
        "run_sp2_mixed_acquisition",
    ),
}


def _module_path(module: str) -> Path:
    path = SOURCE.joinpath(*module.split("."))
    package = path / "__init__.py"
    return package if package.exists() else path.with_suffix(".py")


def _package_modules() -> tuple[str, ...]:
    base = SOURCE.joinpath(*PACKAGE.split("."))
    modules = []
    for path in sorted(base.rglob("*.py")):
        relative = path.relative_to(SOURCE).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules.append(".".join(parts))
    return tuple(modules)


def _imports(module: str, source: str | None = None) -> set[str]:
    """Return every module a module imports, including `TYPE_CHECKING` blocks."""
    path = _module_path(module)
    text = path.read_text(encoding="utf-8") if source is None else source
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            found.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module or ""
            )
            found.add(base)
            found.update(f"{base}.{item.name}" for item in node.names)
    return found


def _graph(modules: tuple[str, ...]) -> dict[str, set[str]]:
    known = set(modules)
    return {
        module: {item for item in _imports(module) if item in known and item != module}
        for module in modules
    }


def _family(module: str) -> str:
    """Return the workflow family a module belongs to, or ""."""
    if not module.startswith(WORKFLOWS + "."):
        return ""
    return module[len(WORKFLOWS) + 1 :].split(".", 1)[0]


def _violations(graph: dict[str, set[str]]) -> list[str]:
    """Name every edge the declared architecture forbids."""
    found = []
    coordinator = f"{PACKAGE}.coordinator"
    execution = f"{PACKAGE}.execution"
    finalization = f"{PACKAGE}.finalization"
    for module, targets in graph.items():
        for target in targets:
            family, target_family = _family(module), _family(target)
            if family and target_family and family != target_family:
                found.append(f"workflow imports workflow: {module} -> {target}")
            if family and target in (coordinator, FACADE):
                found.append(f"workflow imports orchestration: {module} -> {target}")
            if module == execution and (target_family or target == finalization):
                found.append(f"context imports stage or finalization: {target}")
            if module in (*FOUNDATION, *SUPPORT, finalization) and (
                target_family or target == coordinator
            ):
                found.append(f"control imports stage: {module} -> {target}")
            if module in FOUNDATION and target in (execution, finalization, *SUPPORT):
                found.append(f"foundation imports context: {module} -> {target}")
            if target == FACADE:
                found.append(f"package imports the façade: {module}")
    return sorted(found)


def _cycle(graph: dict[str, set[str]]) -> list[str]:
    state: dict[str, int] = {}
    path: list[str] = []

    def visit(node: str) -> list[str]:
        state[node] = 1
        path.append(node)
        for target in sorted(graph.get(node, ())):
            if state.get(target) == 1:
                return [*path[path.index(target) :], target]
            if target not in state:
                found = visit(target)
                if found:
                    return found
        path.pop()
        state[node] = 2
        return []

    for node in sorted(graph):
        if node not in state:
            found = visit(node)
            if found:
                return found
    return []


# -- dependency graph (QR04) --------------------------------------------------


def test_the_package_has_the_declared_owners():
    """Every approved owner exists as its own module."""
    modules = set(_package_modules())
    expected = {
        f"{PACKAGE}.{name}"
        for name in (
            "contracts",
            "operation_budget",
            "ledgered_transport",
            "campaign_authority",
            "record_lifecycle",
            "execution",
            "fixtures",
            "product_support",
            "dhcp_observations",
            "finalization",
            "coordinator",
        )
    }
    assert expected <= modules
    families = {_family(item) for item in modules} - {""}
    assert families >= {
        "engine",
        "https_page",
        "original_dhcp",
        "dhcp_diagnostics",
        "native_pool",
        "native_product",
        "sp1_routed_product",
        "sp2_mixed_product",
        "sp2_remote_relay",
        "fastloop",
        "web_diagnostics",
    }


def test_the_package_graph_is_acyclic_and_respects_the_declared_edges():
    """Workflows import neither one another nor the coordinator or façade."""
    graph = _graph(_package_modules())

    assert _cycle(graph) == []
    assert _violations(graph) == []


def test_the_checker_sees_each_forbidden_edge():
    """Negative controls: each rule fails on a synthetic violating edge."""
    base = _graph(_package_modules())
    samples = {
        f"{WORKFLOWS}.fastloop": f"{WORKFLOWS}.native_pool",
        f"{WORKFLOWS}.engine": f"{PACKAGE}.coordinator",
        f"{WORKFLOWS}.https_page": FACADE,
        f"{PACKAGE}.execution": f"{PACKAGE}.finalization",
        f"{PACKAGE}.product_support": f"{WORKFLOWS}.fastloop",
        f"{PACKAGE}.contracts": f"{PACKAGE}.execution",
    }
    for module, target in samples.items():
        graph = {key: set(value) for key, value in base.items()}
        graph[module].add(target)
        assert _violations(graph), (module, target)
    cyclic = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
    assert _cycle(cyclic) == ["a", "b", "c", "a"]


def test_the_import_reader_resolves_relative_and_type_checking_imports():
    """The graph reader counts relative and `TYPE_CHECKING` imports alike."""
    source = (
        "from typing import TYPE_CHECKING\n"
        "from ..workflows import fastloop\n"
        "if TYPE_CHECKING:\n"
        "    from .execution import Execution\n"
    )
    found = _imports(f"{WORKFLOWS}.engine", source)

    assert f"{WORKFLOWS}.fastloop" in found
    assert f"{WORKFLOWS}.execution.Execution" in found


def test_only_the_coordinator_constructs_the_invocation_context():
    """One mutable context per invocation: nothing else builds Run or Execution."""
    constructors = {"Run", "Execution"}
    builders: dict[str, set[str]] = {}
    for module in _package_modules():
        tree = ast.parse(_module_path(module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in constructors
            ):
                builders.setdefault(node.func.id, set()).add(module)

    assert builders == {
        "Run": {f"{PACKAGE}.coordinator"},
        "Execution": {f"{PACKAGE}.coordinator"},
    }


def test_domain_predicates_import_no_application_or_infrastructure():
    """QR05: the pure evidence predicates depend on the domain alone."""
    for module in DOMAIN_PREDICATES:
        foreign = {
            item
            for item in _imports(module)
            if item.startswith("packet_tracer_mcp.")
            and not item.startswith("packet_tracer_mcp.domain.")
        }
        assert foreign == set(), module


# -- explicit handlers (QR04) ---------------------------------------------------


def test_every_executable_stage_has_exactly_the_former_handler():
    """The table reproduces the former dispatch for every executable stage.

    Declarative stages are refused by request admission before any record,
    so they have no handler; the former chain's `else` could not reach them.
    A stage added later is listed as a named successor, never folded into
    the former table.
    """
    coordinator = importlib.import_module(f"{PACKAGE}.coordinator")
    handlers = coordinator.STAGE_HANDLERS
    executable = {
        stage
        for stage in QualificationStage
        if (definition := stage_definition(stage.value)) is not None
        and definition.executable
    }

    assert not set(SUCCESSOR_HANDLERS) & set(STARTING_HANDLERS)
    expected = {**STARTING_HANDLERS, **SUCCESSOR_HANDLERS}
    assert set(handlers) == executable == set(expected)
    for stage, (module, name) in expected.items():
        owner = importlib.import_module(f"{PACKAGE}.{module}")
        assert handlers[stage] is getattr(owner, name), stage


# -- façade compatibility (QR03) -----------------------------------------------


def test_the_facade_exports_every_starting_name_as_its_canonical_object():
    """Old and new imports reference the same objects, classes and enums."""
    facade = importlib.import_module(FACADE)

    assert set(facade.__all__) == STARTING_PUBLIC_NAMES | set(OPERATOR_TOOLING_NAMES)
    for name in STARTING_PUBLIC_NAMES - {"qualify_server_services"}:
        owner = importlib.import_module(f"{PACKAGE}.{OWNERS[name]}")
        assert getattr(facade, name) is getattr(owner, name), name
    for name, (module, owner_name) in OPERATOR_TOOLING_NAMES.items():
        owner = importlib.import_module(f"{PACKAGE}.{module}")
        assert getattr(facade, name) is getattr(owner, owner_name), name


def test_the_facade_keeps_the_public_entry_signature():
    """The façade owns the entry; its signature is the starting one."""
    facade = importlib.import_module(FACADE)
    signature = inspect.signature(facade.qualify_server_services)

    assert [
        (item.name, item.kind.name, item.default is inspect.Parameter.empty)
        for item in signature.parameters.values()
    ] == [
        ("request", "POSITIONAL_OR_KEYWORD", True),
        ("boundaries", "POSITIONAL_OR_KEYWORD", True),
        ("experimental_capabilities", "KEYWORD_ONLY", True),
    ]
    assert signature.return_annotation == "QualificationResult"


def test_the_facade_holds_no_workflow_implementation():
    """Imports, `__all__` and one delegating entry: nothing else."""
    tree = ast.parse(_module_path(FACADE).read_text(encoding="utf-8"))
    kinds = []
    for node in tree.body[1:]:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        kinds.append(type(node).__name__)
        if isinstance(node, ast.FunctionDef):
            assert node.name == "qualify_server_services"
            statements = node.body[1:]
            assert len(statements) == 1
            assert isinstance(statements[0], ast.Return)
            call = statements[0].value
            assert isinstance(call, ast.Call)
            assert getattr(call.func, "id", "") == "run_qualification"

    assert kinds == ["Assign", "FunctionDef"]


@pytest.mark.parametrize("module", [FACADE, *_package_modules()])
def test_no_module_aliasing_machinery(module):
    """No `sys.modules` aliasing, wildcard export or module `__getattr__`."""
    tree = ast.parse(_module_path(module).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not (
            isinstance(node, ast.Attribute)
            and node.attr == "modules"
            and getattr(node.value, "id", "") == "sys"
        ), module
        assert not (
            isinstance(node, ast.ImportFrom)
            and any(item.name == "*" for item in node.names)
        ), module
        assert not (isinstance(node, ast.FunctionDef) and node.name == "__getattr__"), (
            module
        )


def test_cold_http_consumes_the_ledger_owners_not_the_facade():
    """The cold-HTTP acceptance reaches the budget and transport directly."""
    imports = _imports("packet_tracer_mcp.application.use_cases.accept_cold_http")

    assert FACADE not in imports
    assert f"{PACKAGE}.operation_budget.OperationLedger" in imports
    assert f"{PACKAGE}.ledgered_transport.LedgeredTransport" in imports
