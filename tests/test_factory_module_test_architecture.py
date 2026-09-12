"""Structural guards on how factory-module tests are written.

Two debts are held in place here rather than left to reviewer memory.

The first is duplication of the factory-module wire format. Production decides
the target of an installation; a test that writes that target by hand states
the same identity twice and the two drift. That happened: a fixture resolving
to slot 0 was paired with a hand-written response naming slot 1, production
correctly refused the mismatch, and a large JSON block had to be edited to
repair a test whose behaviour had not changed. The guard below finds that
shape by AST rather than by grepping for strings, so it sees a dict literal
being *constructed* and ignores one being compared against.

The second is the size of `test_factory_module_preparation.py`. It is a
legacy hotspot: too large to be a focal module, not worth splitting in the
middle of live work. The ratchet records what it measures today and fails if
it grows. That number is a debt ceiling, not an endorsement - new behaviours
belong in focal modules named for the responsibility they cover.
"""

from __future__ import annotations

import ast
from pathlib import Path


TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent

# The one module allowed to spell the factory-module wire format.
WIRE_FORMAT_OWNER = TESTS / "support" / "factory_module_cases.py"

# The legacy hotspot, and the size it measured when the ratchet was set.
HOTSPOT = TESTS / "test_factory_module_preparation.py"
HOTSPOT_LINE_CEILING = 1452

# Key sets that identify one factory-module wire shape. A dict literal whose
# keys cover any of these is that shape, whatever the variable is called.
_WIRE_SHAPES: tuple[tuple[str, frozenset[str]], ...] = (
    ("factory module target", frozenset({"container_navigation_path"})),
    ("installation result", frozenset({"attempted", "requested_identity", "native_ack"})),
    ("module container", frozenset({"slot_count", "module_count", "module_entries"})),
    ("module descriptor", frozenset({"model_observed", "physical_views"})),
    ("physical view", frozenset({"slot_num", "module_added"})),
    ("observation envelope", frozenset({"found", "root"})),
)


def _string_keys(node: ast.Dict) -> frozenset[str]:
    return frozenset(
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    )


def _serialised_dicts(tree: ast.AST) -> set[int]:
    """Dict literals handed straight to a JSON serialiser."""

    serialised: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else getattr(node.func, "id", "")
        )
        if name != "dumps":
            continue
        for argument in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(argument, ast.Dict):
                serialised.add(id(argument))
    return serialised


def _label(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.name


def _wire_constructions(path: Path) -> list[str]:
    """Places this module builds a factory-module wire payload itself."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    serialised = _serialised_dicts(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = _string_keys(node)
        for label, marker in _WIRE_SHAPES:
            if not marker <= keys:
                continue
            # A target payload is duplication wherever it appears; the other
            # shapes only count when the test is serialising one, so that
            # asserting against a decoded result stays legal.
            if "container_navigation_path" in keys or id(node) in serialised:
                findings.append(
                    "%s:%d builds a %s payload"
                    % (_label(path), node.lineno, label),
                )
                break
    return findings


def _test_modules() -> list[Path]:
    return sorted(
        path
        for path in TESTS.rglob("*.py")
        if path != WIRE_FORMAT_OWNER and "__pycache__" not in path.parts
    )


def test_the_wire_format_owner_is_the_only_module_that_builds_it() -> None:
    """Only the support module may spell the factory-module wire format."""

    offenders = [
        finding
        for path in _test_modules()
        for finding in _wire_constructions(path)
    ]

    assert offenders == [], (
        "build these through tests/support/factory_module_cases.py instead of "
        "restating the wire format:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_would_catch_a_reintroduced_wire_payload(
    tmp_path: Path,
) -> None:
    """The guard is only worth keeping if it fails on the shape it forbids."""

    offending = tmp_path / "test_regression.py"
    offending.write_text(
        "import json\n"
        "PAYLOAD = json.dumps({\n"
        '    "attempted": True,\n'
        '    "requested_identity": "AC-POWER-SUPPLY",\n'
        '    "native_ack": True,\n'
        '    "target": {"container_navigation_path": [2], "slot_index": 4,\n'
        '               "module_type": 4},\n'
        "})\n",
        encoding="utf-8",
    )

    findings = _wire_constructions(offending)

    assert any("factory module target" in finding for finding in findings)
    assert any("installation result" in finding for finding in findings)


def test_comparing_against_a_decoded_result_is_not_construction(
    tmp_path: Path,
) -> None:
    """Asserting on what production produced must stay legal."""

    innocent = tmp_path / "test_assertion.py"
    innocent.write_text(
        "def test_x(payload, expected_target):\n"
        "    assert payload == {\n"
        '        "attempted": True,\n'
        '        "requested_identity": "AC-POWER-SUPPLY",\n'
        '        "native_ack": True,\n'
        '        "target": expected_target,\n'
        "    }\n",
        encoding="utf-8",
    )

    assert _wire_constructions(innocent) == []


def test_the_legacy_hotspot_does_not_grow() -> None:
    """A debt ceiling on one oversized module, not a budget for all tests.

    New factory-module behaviours belong in a focal module named for the
    responsibility they cover. Lowering this number after a genuine extraction
    is the intended direction; raising it needs a better reason than
    convenience.
    """

    measured = len(HOTSPOT.read_text(encoding="utf-8").splitlines())

    assert measured <= HOTSPOT_LINE_CEILING, (
        "%s grew to %d lines against a ceiling of %d; put new behaviour in a "
        "focal module instead of extending the hotspot"
        % (HOTSPOT.name, measured, HOTSPOT_LINE_CEILING)
    )
