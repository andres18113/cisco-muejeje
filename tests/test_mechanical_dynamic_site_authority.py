"""Dynamic module references are rewritten only at audited, exact base sites.

A callee's name proves nothing about what the name is bound to, so the boundary
never trusts `patch`, `find_spec`, `import_module`, or `monkeypatch` by name. A
dynamic string gains authority only from a site registered in reviewed source and
bound to its repository path, construct, legacy literal, enclosing scope,
occurrence, and the SHA-256 of the exact base text in which it was audited.
"""

from __future__ import annotations

import hashlib
import subprocess

import pytest

from scripts import mechanical_migration
from scripts.mechanical_migration import (
    Classification,
    MechanicalMigrationError,
    Verdict,
    classify_source_change,
    resolve_transformations,
)
from tests.mechanical_migration_fixtures import (
    CANONICAL,
    LEGACY,
    REPOSITORY_ROOT,
    TARGET,
)

AUTHORIZED = resolve_transformations([CANONICAL])
AUTHORED = Classification.SEMANTIC_OR_AUTHORED_CHANGE
# The commit at which the registered dynamic sites were inventoried and audited.
AUDITED_AT = "5330e0dd424bfa746007034ba0672e570cc4ff0f"
# Each audited file with its number of namespace mentions at the audited commit.
# Every mention is an authorized import or registered dynamic site, so a complete
# rename of one of these files is mechanical at its own path.
AUDITED_FILES = {
    "tests/test_cp_scale_live_cli.py": 2,
    "tests/test_cp_scale_live_coordinator.py": 24,
    "tests/test_cp_scale_stage_executor.py": 17,
    "tests/test_e95_e5_capability_evidence.py": 12,
    "tests/test_mutation_transport_ambiguity.py": 8,
}
# Its only dynamic reference is an implicitly concatenated literal, which the
# boundary never rewrites, so the audit did not register it.
UNREGISTERED_CONCATENATION = "tests/test_poe_delivery_qualification.py"

SHADOWED_CALLEES = [
    (
        "function named patch",
        "def patch(target):\n"
        "    return target\n\n\n"
        'value = patch("src.packet_tracer_mcp.foo")\n',
    ),
    (
        "patch rebound to another callable",
        "from recorders import custom_patch\n\n"
        "patch = custom_patch\n"
        'value = patch("src.packet_tracer_mcp.foo")\n',
    ),
    (
        "function named import_module",
        "def import_module(name):\n"
        "    return name\n\n\n"
        'value = import_module("src.packet_tracer_mcp.foo")\n',
    ),
    (
        "method named find_spec",
        "class Fake:\n"
        "    def find_spec(self, name):\n"
        "        return name\n\n\n"
        "find_spec = Fake().find_spec\n"
        'value = find_spec("src.packet_tracer_mcp.foo")\n',
    ),
    (
        "object named monkeypatch",
        "class Recorder:\n"
        "    def setattr(self, target, value):\n"
        "        return target, value\n\n\n"
        "monkeypatch = Recorder()\n"
        'value = monkeypatch.setattr("src.packet_tracer_mcp.foo.VALUE", 1)\n',
    ),
    (
        "object named importlib",
        "from recorders import Recorder\n\n"
        "importlib = Recorder()\n"
        'value = importlib.import_module("src.packet_tracer_mcp.foo")\n',
    ),
    (
        "function named __import__",
        "def __import__(name, fromlist=()):\n"
        "    return name\n\n\n"
        'value = __import__("src.packet_tracer_mcp.foo")\n',
    ),
]

SHADOWED_IDS = [label for label, _ in SHADOWED_CALLEES]

SYNTHETIC_PATH = "pkg/dynamic_sites.py"
SYNTHETIC_BASE = '''"""Dynamic references."""

from importlib import import_module
from importlib.util import find_spec


def first():
    return find_spec("src.packet_tracer_mcp.foo")


def second():
    return import_module("src.packet_tracer_mcp.foo")


def third():
    return find_spec("src.packet_tracer_mcp.foo")
'''


def _sha256(source: str) -> str:
    """Return the SHA-256 of a text's UTF-8 bytes."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _audited_source(path: str) -> str:
    """Return a file's exact stored text at the audited commit."""
    return subprocess.run(
        ["git", "cat-file", "blob", f"{AUDITED_AT}:{path}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")


def _rename(source: str) -> str:
    """Rename every namespace mention, as a complete migration of a file would."""
    return source.replace(LEGACY, TARGET)


def _synthetic_site(**overrides: object) -> mechanical_migration.AuditedDynamicSite:
    """Return an audited site for the synthetic source, with field overrides."""
    fields: dict[str, object] = {
        "path": SYNTHETIC_PATH,
        "base_sha256": _sha256(SYNTHETIC_BASE),
        "scope": "first",
        "callee": "find_spec",
        "argument": 0,
        "literal": "src.packet_tracer_mcp.foo",
        "occurrence": 0,
    }
    fields.update(overrides)
    return mechanical_migration.AuditedDynamicSite(**fields)


def _synthetic_transformation(
    *sites: mechanical_migration.AuditedDynamicSite,
) -> tuple[mechanical_migration.MechanicalTransformation, ...]:
    """Build a namespace transformation authorizing exactly the given sites."""
    return (
        mechanical_migration.namespace_transformation(
            identifier="AUDITED_TEST_NAMESPACE",
            summary="Rename the test namespace at audited sites.",
            authority="tests/test_mechanical_dynamic_site_authority.py",
            legacy=LEGACY,
            canonical=TARGET,
            audited_sites=sites,
        ),
    )


def _classify_synthetic(
    candidate: str,
    *sites: mechanical_migration.AuditedDynamicSite,
    base: str = SYNTHETIC_BASE,
    path: str = SYNTHETIC_PATH,
) -> Verdict:
    """Classify a synthetic delta against a transformation holding the sites."""
    return classify_source_change(
        base,
        candidate,
        _synthetic_transformation(*sites),
        path=path,
    )


def _rename_in_scope(source: str, scope: str) -> str:
    """Rename the literal inside one synthetic function only."""
    header = f"def {scope}():\n"
    start = source.index(header)
    end = source.find("\ndef ", start + len(header))
    end = len(source) if end == -1 else end
    return source[:start] + _rename(source[start:end]) + source[end:]


@pytest.mark.parametrize(("label", "source"), SHADOWED_CALLEES, ids=SHADOWED_IDS)
def test_shadowed_callee_name_grants_no_authority(label: str, source: str) -> None:
    """Refuse a dynamic rewrite whose only credential is the callee's name."""
    verdict = classify_source_change(source, _rename(source), AUTHORIZED)

    assert verdict.classification is AUTHORED, label
    assert not verdict.is_exempt


@pytest.mark.parametrize("path", [*sorted(AUDITED_FILES), "tests/test_shadowed.py"])
@pytest.mark.parametrize(("label", "source"), SHADOWED_CALLEES, ids=SHADOWED_IDS)
def test_shadowed_callee_at_any_path_grants_no_authority(
    label: str,
    source: str,
    path: str,
) -> None:
    """Refuse a shadowed callee even at the path of an audited file."""
    verdict = classify_source_change(source, _rename(source), AUTHORIZED, path=path)

    assert verdict.classification is AUTHORED, label


@pytest.mark.parametrize("path", sorted(AUDITED_FILES))
def test_audited_dynamic_sites_are_mechanical_at_their_registered_path(
    path: str,
) -> None:
    """Accept the real audited sites, with every import, at their own file."""
    base = _audited_source(path)

    verdict = classify_source_change(base, _rename(base), AUTHORIZED, path=path)

    assert verdict.classification is Classification.MECHANICAL_ONLY
    assert verdict.applied_sites == AUDITED_FILES[path]


@pytest.mark.parametrize("path", sorted(AUDITED_FILES))
def test_audited_dynamic_sites_without_a_path_are_authored(path: str) -> None:
    """Refuse dynamic rewrites when the classifier is not told which file it reads."""
    base = _audited_source(path)

    verdict = classify_source_change(base, _rename(base), AUTHORIZED)

    assert verdict.classification is AUTHORED


@pytest.mark.parametrize(
    "path",
    ["tests/test_copied_sites.py", "tests/test_cp_scale_live_coordinator.py"],
)
def test_audited_file_copied_to_another_path_is_authored(path: str) -> None:
    """Refuse the same dynamic literals and constructs in a different file."""
    base = _audited_source("tests/test_cp_scale_stage_executor.py")

    verdict = classify_source_change(base, _rename(base), AUTHORIZED, path=path)

    assert verdict.classification is AUTHORED


def test_shadowing_added_to_an_audited_file_voids_its_dynamic_authority() -> None:
    """Refuse registered sites once the base text differs from the audited text."""
    path = "tests/test_cp_scale_stage_executor.py"
    base = _audited_source(path) + "\n\ndef find_spec(name):\n    return name\n"

    verdict = classify_source_change(base, _rename(base), AUTHORIZED, path=path)

    assert verdict.classification is AUTHORED


def test_functional_change_beside_audited_sites_is_authored() -> None:
    """Refuse a registered file whose rename carries a behavioral edit."""
    path = "tests/test_cp_scale_stage_executor.py"
    base = _audited_source(path)
    candidate = _rename(base).replace("is not None", "is None", 1)
    assert candidate != _rename(base)

    verdict = classify_source_change(base, candidate, AUTHORIZED, path=path)

    assert verdict.classification is AUTHORED


def test_audited_literal_renamed_to_another_module_is_authored() -> None:
    """Refuse a registered site rewritten to anything but the canonical name."""
    path = "tests/test_mutation_transport_ambiguity.py"
    base = _audited_source(path)
    candidate = _rename(base).replace(
        '"packet_tracer_mcp.adapters.mcp.tool_registry"',
        '"packet_tracer_mcp.adapters.mcp.other_registry"',
    )
    assert candidate != _rename(base)

    verdict = classify_source_change(base, candidate, AUTHORIZED, path=path)

    assert verdict.classification is AUTHORED


def test_unregistered_concatenated_literal_keeps_its_file_authored() -> None:
    """Keep the audited exclusion: a concatenated dynamic literal is never proven."""
    base = _audited_source(UNREGISTERED_CONCATENATION)

    verdict = classify_source_change(
        base,
        _rename(base),
        AUTHORIZED,
        path=UNREGISTERED_CONCATENATION,
    )

    assert verdict.classification is AUTHORED


def test_registered_sites_match_the_audited_commit() -> None:
    """Bind every registered site to the exact stored text it was audited in."""
    (transformation,) = AUTHORIZED
    sites = transformation.audited_sites

    assert transformation.audited_at == AUDITED_AT
    assert {site.path for site in sites} == set(AUDITED_FILES)
    assert len(sites) == 8
    for site in sites:
        source = _audited_source(site.path)
        assert site.base_sha256 == _sha256(source), site.path
        assert f'"{site.literal}"' in source, site.path


def test_only_the_registered_synthetic_site_is_mechanical() -> None:
    """Accept exactly the one audited site of a synthetic source."""
    verdict = _classify_synthetic(
        _rename_in_scope(SYNTHETIC_BASE, "first"),
        _synthetic_site(),
    )

    assert verdict.classification is Classification.MECHANICAL_ONLY
    assert verdict.applied_sites == 1


def test_same_path_with_a_different_construct_is_authored() -> None:
    """Refuse a site whose registered callee differs from the construct in the base."""
    verdict = _classify_synthetic(
        _rename_in_scope(SYNTHETIC_BASE, "first"),
        _synthetic_site(callee="import_module"),
    )

    assert verdict.classification is AUTHORED


def test_unregistered_construct_beside_a_registered_site_is_authored() -> None:
    """Refuse a second construct with the same literal that the audit never named."""
    candidate = _rename_in_scope(
        _rename_in_scope(SYNTHETIC_BASE, "first"),
        "second",
    )

    verdict = _classify_synthetic(candidate, _synthetic_site())

    assert verdict.classification is AUTHORED


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("other scope", {"scope": "third"}),
        ("other literal", {"literal": "src.packet_tracer_mcp.bar"}),
        ("other occurrence", {"occurrence": 1}),
        ("other argument", {"argument": "name"}),
        ("other base text", {"base_sha256": _sha256(SYNTHETIC_BASE + "\n")}),
        ("other path", {"path": "pkg/other_sites.py"}),
    ],
)
def test_site_that_does_not_match_exactly_grants_nothing(
    label: str,
    overrides: dict[str, object],
) -> None:
    """Refuse the rewrite when any bound field of the audited site differs."""
    verdict = _classify_synthetic(
        _rename_in_scope(SYNTHETIC_BASE, "first"),
        _synthetic_site(**overrides),
    )

    assert verdict.classification is AUTHORED, label


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("unrecognized construct", {"callee": "record"}),
        ("unrecognized argument", {"argument": 1}),
        ("literal outside the namespace", {"literal": "packet_tracer_mcp.foo"}),
        ("abbreviated base hash", {"base_sha256": "abc123"}),
        ("absolute path", {"path": "/pkg/dynamic_sites.py"}),
        ("parent path", {"path": "../pkg/dynamic_sites.py"}),
        ("negative occurrence", {"occurrence": -1}),
    ],
)
def test_malformed_audited_site_cannot_be_registered(
    label: str,
    overrides: dict[str, object],
) -> None:
    """Reject an audited site the transformation could never honor exactly."""
    with pytest.raises(MechanicalMigrationError):
        _synthetic_transformation(_synthetic_site(**overrides))
