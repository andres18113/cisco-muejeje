"""Layering and separation guarantees for the wireless connectivity feature.

These are the invariants that stop the design from eroding: the domain has to
stay backend-neutral, the function axis has to stay structurally separate from
the association axis, and no module may hardcode the topology that happened to
motivate the work.
"""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.wireless_connectivity import (
    IoTFunctionDeclaration,
    WirelessAssociationObservation,
    WirelessAssociationState,
    WirelessCapabilityStatus,
    NetworkAttachmentState,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "packet_tracer_mcp"

DOMAIN_MODULES = (
    PACKAGE / "domain/enterprise/models/wireless_connectivity.py",
    PACKAGE / "domain/enterprise/rules/wireless_connectivity.py",
    PACKAGE / "domain/enterprise/services/wireless_cluster_planner.py",
)
APPLICATION_MODULES = (
    PACKAGE / "application/ports/wireless_connectivity.py",
    PACKAGE / "application/use_cases/plan_iot_connectivity.py",
)
INFRASTRUCTURE_MODULES = (
    PACKAGE / "infrastructure/catalog/wireless_capabilities.py",
    PACKAGE / "infrastructure/execution/packet_tracer_wireless_connectivity.py",
)


def _code_text(path: Path) -> str:
    """Source without docstrings, so prose about a backend is not a dependency."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    parts: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                parts.append(node.value)
        elif isinstance(node, ast.Name):
            parts.append(node.id)
        elif isinstance(node, ast.Attribute):
            parts.append(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            parts.append(" ".join(sorted(_imports(path))))
    return chr(10).join(parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.add(("." * node.level) + (node.module or ""))
    return result


@pytest.mark.parametrize(
    "path", DOMAIN_MODULES, ids=lambda item: item.name,
)
def test_the_wireless_domain_never_imports_a_backend(path):
    forbidden = sorted(
        item for item in _imports(path)
        if "infrastructure" in item or "adapters" in item
    )

    assert forbidden == []


@pytest.mark.parametrize(
    "path", DOMAIN_MODULES, ids=lambda item: item.name,
)
def test_the_wireless_domain_never_names_packet_tracer(path):
    """Docstrings may explain the boundary; code may not cross it."""
    code = _code_text(path).casefold()

    assert "packet tracer" not in code
    assert "packet_tracer" not in code
    assert "ipc.network" not in code
    assert "getport" not in code


@pytest.mark.parametrize(
    "path", APPLICATION_MODULES, ids=lambda item: item.name,
)
def test_the_application_layer_depends_on_the_port_not_an_adapter(path):
    imports = _imports(path)

    assert not any("infrastructure" in item for item in imports)
    assert not any("adapters" in item for item in imports)


def test_only_infrastructure_holds_the_packet_tracer_capability_audit():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in (*DOMAIN_MODULES, *APPLICATION_MODULES)
        if "packet_tracer_wireless_capability_audit" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


@pytest.mark.parametrize(
    "path", (*DOMAIN_MODULES, *APPLICATION_MODULES, *INFRASTRUCTURE_MODULES),
    ids=lambda item: item.name,
)
def test_no_wireless_module_hardcodes_the_topology_that_motivated_it(path):
    source = path.read_text(encoding="utf-8")
    lowered = source.casefold()

    assert "vlan 30" not in lowered
    for literal in ("vlan_id=30", "vlan_id = 30"):
        assert literal not in source


@pytest.mark.parametrize(
    "path", (*DOMAIN_MODULES, *APPLICATION_MODULES), ids=lambda item: item.name,
)
def test_the_reusable_contract_does_not_know_the_reference_topology(path):
    """Infrastructure may cite the governed policy; the contract may not."""
    lowered = path.read_text(encoding="utf-8").casefold()

    assert "cp-scale" not in lowered
    assert "cp_scale" not in lowered
    assert "cp-live" not in lowered


def test_no_wireless_module_names_a_device_count_or_a_site_name():
    """A count that belongs to one topology has no place in the contract."""
    for path in (*DOMAIN_MODULES, *APPLICATION_MODULES, *INFRASTRUCTURE_MODULES):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        numbers = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, int)
            and not isinstance(node.value, bool)
        }
        # Only structural small integers are acceptable anywhere here.
        assert numbers <= {0, 1, 2}, (path.name, sorted(numbers))


def test_the_iot_function_declaration_cannot_carry_association_evidence():
    names = {item.name for item in fields(IoTFunctionDeclaration)}

    assert names == {"endpoint_id", "function", "observation_status", "note"}
    assert not names & {
        item.name for item in fields(WirelessAssociationObservation)
    } - {"endpoint_id", "observation_status"}


def test_the_two_state_vocabularies_stay_distinct():
    """Association and attachment share a lifecycle shape, not a verdict."""
    association = {item.value for item in WirelessAssociationState}
    attachment = {item.value for item in NetworkAttachmentState}

    assert "associated" in association
    assert "associated" not in attachment
    assert "attached" in attachment
    assert "attached" not in association
    assert association - {"associated"} == attachment - {"attached"}


def test_the_capability_vocabulary_keeps_its_classes_distinct():
    assert {item.value for item in WirelessCapabilityStatus} == {
        "supported", "documented", "unsupported", "unknown", "unobservable",
    }


def test_the_cp_live_closure_is_untouched_by_this_feature():
    """CP-LIVE keeps wireless association unqualified; nothing here reopens it."""
    policy = (
        PACKAGE / "infrastructure/catalog/cp_scale_qualification_policy.py"
    ).read_text(encoding="utf-8")

    assert "wireless_association=Status.UNQUALIFIED" in policy
    assert "wireless_connectivity" not in policy
