"""Contract of the fail-closed preflight that guards this checkout's test process.

The preflight decides one thing: may this process trust what it is about to
test?  It answers from three observations -- which environment owns the running
interpreter, where the production package actually resolved, and whether a
second identity of the same source is loaded -- and any doubt is a refusal.

The decision rule is exercised here with injected observations, so every
rejection is reachable without building a second environment.  One end-to-end
test then runs the real rule in a child process against a foreign root, which
is the shape the historical defect actually took: a `.venv` belonging to
another checkout silently resolving that other checkout's source.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.namespace_preflight import (
    LEGACY_NAMESPACE,
    PRODUCTION_NAMESPACE,
    NamespacePreflight,
    NamespacePreflightError,
    NamespacePreflightState,
)

CHECKOUT = Path(__file__).resolve().parents[1]
ENVIRONMENT = CHECKOUT / ".venv"
PACKAGE_FILE = CHECKOUT / "src" / PRODUCTION_NAMESPACE / "__init__.py"


def _preflight(
    *,
    checkout_root: Path = CHECKOUT,
    executable: Path = ENVIRONMENT / "Scripts" / "python.exe",
    environment_prefix: Path = ENVIRONMENT,
    package_file: Path | None = PACKAGE_FILE,
    loaded: tuple[str, ...] = (PRODUCTION_NAMESPACE,),
) -> NamespacePreflight:
    """Build the rule over fully declared observations."""
    return NamespacePreflight(
        checkout_root,
        executable=lambda: str(executable),
        environment_prefix=lambda: str(environment_prefix),
        resolve_package_file=lambda: (
            None if package_file is None else str(package_file)
        ),
        loaded_namespaces=lambda: frozenset(loaded),
    )


def test_this_checkouts_environment_and_package_are_accepted():
    """The positive control: this checkout judging itself."""
    result = _preflight().evaluate()

    assert result.state is NamespacePreflightState.ISOLATED
    assert result.accepted


def test_an_environment_owned_by_another_checkout_is_refused():
    """The historical defect: another checkout's `.venv` resolving its own source."""
    foreign = CHECKOUT.parent / "Cisco-MCP-other"

    result = _preflight(
        executable=foreign / ".venv" / "Scripts" / "python.exe",
        environment_prefix=foreign / ".venv",
    ).evaluate()

    assert result.state is NamespacePreflightState.FOREIGN_INTERPRETER
    assert str(foreign) in result.detail


def test_an_interpreter_outside_its_declared_environment_is_refused():
    """A checkout-local prefix does not license an interpreter from elsewhere."""
    result = _preflight(
        executable=Path(sys.base_prefix) / "python.exe",
    ).evaluate()

    assert result.state is NamespacePreflightState.FOREIGN_INTERPRETER


def test_an_editable_install_pointing_at_another_checkout_is_refused():
    """This checkout's `.venv`, but a `.pth` that still names the old tree."""
    foreign_origin = (
        CHECKOUT.parent
        / "Cisco-MCP-other"
        / "src"
        / PRODUCTION_NAMESPACE
        / "__init__.py"
    )

    result = _preflight(package_file=foreign_origin).evaluate()

    assert result.state is NamespacePreflightState.FOREIGN_PACKAGE_ORIGIN
    assert str(foreign_origin) in result.detail


def test_a_package_that_did_not_resolve_is_refused_rather_than_assumed():
    """An unresolved package is unknown, never an implicit pass."""
    result = _preflight(package_file=None).evaluate()

    assert result.state is NamespacePreflightState.PRODUCTION_PACKAGE_UNRESOLVED


def test_both_namespaces_loaded_at_once_is_refused():
    """Two identities over the same files is the defect this migration removes."""
    result = _preflight(loaded=(PRODUCTION_NAMESPACE, LEGACY_NAMESPACE)).evaluate()

    assert result.state is NamespacePreflightState.LEGACY_NAMESPACE_LOADED
    assert LEGACY_NAMESPACE in result.detail


def test_the_legacy_namespace_alone_is_refused():
    """After the migration the legacy name is not an alternative identity."""
    result = _preflight(loaded=(LEGACY_NAMESPACE,)).evaluate()

    assert result.state is NamespacePreflightState.LEGACY_NAMESPACE_LOADED


def test_an_unreadable_observation_is_refused_not_passed():
    """Fail closed: an error while observing is never a licence to continue."""

    def explode() -> str:
        raise OSError("the environment could not be read")

    preflight = NamespacePreflight(
        CHECKOUT,
        executable=explode,
        environment_prefix=lambda: str(ENVIRONMENT),
        resolve_package_file=lambda: str(PACKAGE_FILE),
        loaded_namespaces=lambda: frozenset({PRODUCTION_NAMESPACE}),
    )

    result = preflight.evaluate()

    assert result.state is NamespacePreflightState.INDETERMINATE
    assert not result.accepted


def test_enforce_raises_with_the_expected_and_observed_values():
    """A refusal has to say what was expected and what was seen."""
    foreign = CHECKOUT.parent / "Cisco-MCP-other"
    preflight = _preflight(
        executable=foreign / ".venv" / "Scripts" / "python.exe",
        environment_prefix=foreign / ".venv",
    )

    with pytest.raises(NamespacePreflightError) as failure:
        preflight.enforce()

    message = str(failure.value)
    assert "FOREIGN_INTERPRETER" in message
    assert str(CHECKOUT) in message
    assert str(foreign) in message


def test_enforce_returns_the_accepted_result():
    """An accepted run gets the result back rather than an exception."""
    assert _preflight().enforce().accepted


def test_the_real_rule_refuses_this_environment_against_a_foreign_checkout(tmp_path):
    """End-to-end, in a child process, with nothing injected.

    `tmp_path` stands for another checkout.  The running interpreter belongs to
    this one, so from that root it is exactly a foreign `.venv` -- the condition
    a copied or inherited environment produces.
    """
    source = (
        "import json, sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(CHECKOUT)!r})\n"
        "from tests.namespace_preflight import NamespacePreflight\n"
        "root = Path(sys.argv[1])\n"
        "result = NamespacePreflight(root).evaluate()\n"
        'print(json.dumps({"state": result.state.value, "detail": result.detail,\n'
        '                  "rendered": result.render(root.resolve())}))\n'
    )

    completed = subprocess.run(
        [sys.executable, "-c", source, str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    observation = json.loads(completed.stdout)
    assert observation["state"] == NamespacePreflightState.FOREIGN_INTERPRETER.value
    # The refusal names both sides: the checkout that was expected to own the
    # environment, and the environment that actually ran.
    assert str(tmp_path) in observation["rendered"]
    assert str(CHECKOUT / ".venv") in observation["detail"]


def test_the_real_rule_accepts_this_checkout_from_its_own_root():
    """The positive control of the same end-to-end path."""
    source = (
        "import json, sys\n"
        "from tests.namespace_preflight import NamespacePreflight\n"
        "result = NamespacePreflight(sys.argv[1]).evaluate()\n"
        'print(json.dumps({"state": result.state.value, "detail": result.detail}))\n'
    )

    completed = subprocess.run(
        [sys.executable, "-c", source, str(CHECKOUT)],
        cwd=CHECKOUT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    observation = json.loads(completed.stdout)
    assert observation["state"] == NamespacePreflightState.ISOLATED.value
    assert observation["detail"] == str(PACKAGE_FILE)
