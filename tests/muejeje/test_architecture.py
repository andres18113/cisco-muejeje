"""Architecture fitness gates for Muejeje-owned code.

These are the M0F gates. They apply to Muejeje-owned code **going forward** —
the owned source root, the build auditor, its CLI and this test area — and
deliberately not to unrelated legacy code, which was written under no such
budget (MJ-020, MJ-021). Modular cohesion and dependency direction are the
same family of gate and live in `test_auditor_layers`.

Two budgets per file type: a *target* every file is expected to meet, and a
*hard limit* nothing may cross. A file over target needs a named justification
in `TARGET_EXCEPTIONS`; there is no exception table for the hard limit, because
crossing it is meant to require editing this gate and saying why in the diff.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.muejeje.measure import (
    engine_sources,
    js_function_lengths,
    python_function_lengths,
    relative,
    source_lines,
)
from tests.muejeje.support import (
    CLI,
    MUEJEJE_TESTS,
    PTS_PACKAGE,
    REPO_ROOT,
)

MODULE_TARGET, MODULE_HARD = 300, 500
TEST_TARGET, TEST_HARD = 300, 500
JS_TARGET, JS_HARD = 250, 400
FUNCTION_TARGET, FUNCTION_HARD = 40, 80

# path -> why this file may exceed its target. Empty: nothing needs one.
TARGET_EXCEPTIONS: dict[str, str] = {}
# "path::function" -> why this function may exceed the target.
FUNCTION_EXCEPTIONS: dict[str, str] = {
    "muejeje_pts/script-engine/210_dispatcher_v6.js::muejejeV6OperationTable": (
        "the V6 whitelist, and it is a declaration rather than logic: no "
        "branch, no loop, one entry per admitted operation, so its length is "
        "the number of operations and not the amount a reader must follow. "
        "Splitting it would split the whitelist, which is the one thing that "
        "has to be readable in a single place (MJ-008) — and the table is "
        "already the only place a reader can see the whole of what this "
        "runtime admits."
    ),
}

# Modules in the test area that carry fixtures, measurement or a harness
# rather than claims. Everything else there must be a test module.
#
# `measure.py` was split out of `support.py`, and `platform_stub.py` out of
# `engine_harness.py`, each when its predecessor crossed its own line budget.
# Building a fixture, measuring a file, running the kernel and building a
# platform for it to talk to are four responsibilities, and the budget is what
# forced each split instead of letting it be argued about (MJ-018, MJ-020).
SUPPORT_MODULES = {
    "support.py", "measure.py", "engine_harness.py", "platform_stub.py",
}

# The monolith M0F broke up. Its absence is part of the gate: moving the same
# oversized responsibility into a new file is not a fix.
RETIRED_TEST_MODULES = (
    "tests/test_muejeje_build.py",
    "tests/test_muejeje_build_identity.py",
    "tests/test_muejeje_source_root.py",
)


def owned_python_modules() -> list[Path]:
    return sorted(PTS_PACKAGE.glob("*.py")) + [CLI]


def owned_test_modules() -> list[Path]:
    return sorted(MUEJEJE_TESTS.glob("*.py"))


def _budget(path: Path) -> tuple[int, int]:
    if path.suffix == ".js":
        return JS_TARGET, JS_HARD
    if path.is_relative_to(MUEJEJE_TESTS):
        return TEST_TARGET, TEST_HARD
    return MODULE_TARGET, MODULE_HARD


def owned_files() -> list[Path]:
    return owned_python_modules() + owned_test_modules() + engine_sources()


# ---------------------------------------------------------------------------
# Complexity budgets.
# ---------------------------------------------------------------------------

def test_no_owned_file_crosses_its_hard_loc_limit():
    offenders: list[str] = []
    for path in owned_files():
        _, hard = _budget(path)
        lines = source_lines(path)
        if lines > hard:
            offenders.append(f"{relative(path)}: {lines} > {hard}")
    assert not offenders, (
        "a hard-limit exception requires an explicit architectural "
        f"justification in this gate, not a bigger file: {offenders}"
    )


def test_owned_files_meet_their_target_or_name_an_exception():
    offenders: list[str] = []
    for path in owned_files():
        target, _ = _budget(path)
        lines = source_lines(path)
        justification = TARGET_EXCEPTIONS.get(relative(path), "")
        if lines > target and not justification:
            offenders.append(f"{relative(path)}: {lines} > {target}")
    assert not offenders, f"over target with no stated justification: {offenders}"


def test_target_exception_table_carries_no_stale_entry():
    """An exception that no longer applies is a claim nobody is checking."""
    for logical, justification in TARGET_EXCEPTIONS.items():
        path = REPO_ROOT / logical
        assert path.is_file(), logical
        assert justification.strip(), logical
        target, _ = _budget(path)
        assert source_lines(path) > target, (
            f"{logical} now meets its target; drop the exception"
        )


def test_the_function_exception_table_carries_no_stale_entry():
    """An exception that no longer applies is a claim nobody is checking.

    The same rule the file-level table is held to. Without it, a function that
    shrank back under the target would keep a standing permission to grow, and
    the next reader would have no way to tell an argued exception from an
    inherited one.
    """
    measured = dict(_function_offenders(0, honour_exceptions=False, keys_only=True))
    for key, justification in FUNCTION_EXCEPTIONS.items():
        assert justification.strip(), key
        assert key in measured, f"{key} no longer exists; drop the exception"
        assert measured[key] > FUNCTION_TARGET, (
            f"{key} now meets the target; drop the exception"
        )


def _function_offenders(
    limit: int, *, honour_exceptions: bool, keys_only: bool = False,
) -> list[str]:
    offenders: list[str] = []
    measured: list[tuple[Path, list[tuple[str, int]]]] = [
        (path, python_function_lengths(path))
        for path in owned_python_modules() + owned_test_modules()
    ]
    measured += [(path, js_function_lengths(path)) for path in engine_sources()]
    for path, functions in measured:
        for name, span in functions:
            key = f"{relative(path)}::{name}"
            if honour_exceptions and FUNCTION_EXCEPTIONS.get(key, "").strip():
                continue
            if keys_only:
                offenders.append((key, span))
            elif span > limit:
                offenders.append(f"{key}: {span} > {limit}")
    return offenders


def test_no_owned_function_crosses_the_hard_limit():
    assert not _function_offenders(FUNCTION_HARD, honour_exceptions=False)


def test_owned_functions_meet_the_target_or_name_an_exception():
    offenders = _function_offenders(FUNCTION_TARGET, honour_exceptions=True)
    assert not offenders, (
        f"a function this long is doing more than one thing: {offenders}"
    )


def test_the_function_budget_measures_branching_not_explaining():
    """`classify_build_state` is a short decision with a long docstring.

    Its physical span is well over the target and its code is well under it. If
    the measurement ever starts counting the docstring, this gate would push
    someone to delete the explanation to satisfy it, so the difference between
    the two numbers is asserted rather than assumed.
    """
    module = REPO_ROOT / "src/packet_tracer_mcp/infrastructure/pts/build_state.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "classify_build_state"
    )
    physical = (node.end_lineno or node.lineno) - node.lineno + 1
    measured = dict(python_function_lengths(module))["classify_build_state"]

    assert physical > FUNCTION_TARGET, "the case this gate exists for is gone"
    assert measured <= FUNCTION_TARGET


# ---------------------------------------------------------------------------
# Tests stay separated by responsibility.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("retired", RETIRED_TEST_MODULES)
def test_the_monolithic_muejeje_test_module_is_gone(retired: str):
    assert not (REPO_ROOT / retired).exists(), (
        f"{retired} was split by responsibility; it must not come back"
    )


def test_muejeje_tests_live_in_their_own_area_and_stay_plural():
    modules = {path.name for path in owned_test_modules()}
    assert SUPPORT_MODULES <= modules
    responsibilities = modules - SUPPORT_MODULES
    assert len(responsibilities) >= 4, (
        f"one giant integration file is what M0F removed: {sorted(responsibilities)}"
    )
    for name in responsibilities:
        assert name.startswith("test_"), (
            f"{name} is neither a test module nor a declared support module"
        )


@pytest.mark.parametrize("support", sorted(SUPPORT_MODULES))
def test_a_support_module_asserts_nothing_of_its_own(support: str):
    """Fixtures build; tests claim. A helper that asserts hides the claim.

    A guard *inside* a harness is different from a behaviour claim: the Node
    harness asserts that Node was checked for and that the kernel did not throw
    out of the engine, which are preconditions for the caller's claim rather
    than the claim itself. Those two are named here so a third one cannot
    appear unnoticed.
    """
    allowed_guards = (
        "assert node is not None",
        "assert completed.returncode == 0",
    )
    body = (MUEJEJE_TESTS / support).read_text(encoding="utf-8")
    assert "def test_" not in body
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("assert "):
            continue
        assert stripped.startswith(allowed_guards), f"{support}: {stripped}"


def test_every_muejeje_test_module_states_its_responsibility():
    for path in owned_test_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert ast.get_docstring(tree), (
            f"{relative(path)} must say which responsibility it covers"
        )
