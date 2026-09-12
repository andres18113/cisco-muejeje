"""The build audit runs the auditor's source, never bytecode left beside it.

`tools/build_muejeje_pts.py` issues `PACKAGING_MANUAL_AVAILABLE` and the recipe
id, so it is the one command whose own code has to be the code in the checkout.
Ordinary imports do not guarantee that: Python executes a timestamp-based
`.pyc` whenever it records the source's mtime and size, so a moved or restored
tree can run bytecode compiled from other contents. A moved worktree on this
line kept exactly such an entry — a valid header in front of different code.

These tests reproduce that failure instead of asserting a setting. A disposable
copy of the auditor gets a `build_state.py` whose adjacent cache was compiled
from a forged classifier — every build available — and records the current
source's exact size and mtime. Imported the ordinary way, that copy issues a
forged `PACKAGING_MANUAL_AVAILABLE` with a recipe id. The governed entry point,
over the same trees, must report what the current source decides.
"""

from __future__ import annotations

import importlib.util
import json
import os
import py_compile
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.muejeje.support import CLI, REPO_ROOT, build_api, make_repo

POISONED = Path("packet_tracer_mcp/infrastructure/pts/build_state.py")
POISONED_MODULE = "packet_tracer_mcp.infrastructure.pts.build_state"
MANIFEST = "muejeje_pts/manifest/muejeje-build-manifest.json"
REPORT = "dist/muejeje.build.json"
BYTECODE_DIRECTORY_PREFIX = "muejeje-audit-pycache-"
PROBE = "MUEJEJE_BYTECODE_PROBE"
# What a child must not inherit about bytecode or import paths.
INHERITED = frozenset({"PYTHONPATH", "PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE"})

# Appended to the stale contents only. Whatever the facts, every build is
# available: the verdict a stale auditor must never be able to issue.
FORGED_CLASSIFIER = (
    b"\n\ndef classify_build_state(**_facts):\n"
    b"    return PACKAGING_MANUAL_AVAILABLE\n"
)
# Appended to the current contents only: where this module's bytecode went.
CURRENT_PROBE = (
    f"\n\nimport os as _os\nif _os.environ.get({PROBE!r}):\n"
    f"    with open(_os.environ[{PROBE!r}], 'a', encoding='utf-8') as _probe:\n"
    "        _probe.write(__spec__.cached + '\\n')\n"
).encode()
# What the entry point did before it isolated bytecode: import the auditor the
# ordinary way, and inspect.
ORDINARY_AUDIT = (
    "import json, pathlib\n"
    "from packet_tracer_mcp.infrastructure.pts import inspect_build\n"
    "root = pathlib.Path.cwd().resolve()\n"
    f"report = inspect_build(root, root / {MANIFEST!r})\n"
    "print(json.dumps([report['status'], report['build_recipe_id']]))\n"
)


@dataclass(frozen=True)
class Trees:
    """A synthetic checkout to audit, and a poisoned copy of the auditor."""

    checkout: Path
    auditor: Path
    module: Path
    cache: Path
    temp: Path


@pytest.fixture
def poisoned(tmp_path: Path) -> Trees:
    checkout, _ = make_repo(tmp_path)
    auditor = tmp_path / "auditor"
    shutil.copytree(
        REPO_ROOT / "src/packet_tracer_mcp", auditor / "packet_tracer_mcp",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    module = auditor / POISONED
    original = module.read_bytes()
    cache = _poison(
        module, current=original + CURRENT_PROBE, stale=original + FORGED_CLASSIFIER,
    )
    temp = tmp_path / "temp"
    temp.mkdir()
    return Trees(checkout, auditor, module, cache, temp.resolve())


def _poison(module: Path, *, current: bytes, stale: bytes) -> Path:
    """Leave `module` holding `current`, beside bytecode compiled from `stale`.

    Both are padded to one length, and the source gets back the mtime it had
    when the bytecode was compiled. The cache then records exactly the size and
    mtime of the current source — the two facts Python checks before it
    executes a timestamp-based `.pyc`.
    """
    width = max(len(current), len(stale))
    tag = sys.implementation.cache_tag
    cache = module.parent / "__pycache__" / f"{module.stem}.{tag}.pyc"
    module.write_bytes(stale.ljust(width, b"#"))
    py_compile.compile(
        str(module), cfile=str(cache), doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    compiled = module.stat()
    module.write_bytes(current.ljust(width, b"#"))
    os.utime(module, ns=(compiled.st_atime_ns, compiled.st_mtime_ns))
    return cache


def _environment(
    temp: Path, *, import_path: tuple[Path, ...] = (), **extra: str,
) -> dict[str, str]:
    environment = {
        name: value for name, value in os.environ.items() if name not in INHERITED
    }
    environment.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp), **extra)
    if import_path:
        environment["PYTHONPATH"] = os.pathsep.join(map(str, import_path))
    return environment


def _run(arguments: list[str], cwd: Path, environment: dict[str, str]):
    return subprocess.run(
        [sys.executable, *arguments], cwd=cwd, env=environment,
        text=True, capture_output=True, timeout=120,
    )


def _governed_audit(trees: Trees, *, import_path: tuple[Path, ...] = (), **extra: str):
    path = import_path or (trees.auditor,)
    environment = _environment(trees.temp, import_path=path, **extra)
    return _run([str(CLI), "--check"], trees.checkout, environment)


def _ordinary_audit(trees: Trees) -> list:
    environment = _environment(trees.temp, import_path=(trees.auditor,))
    completed = _run(["-c", ORDINARY_AUDIT], trees.checkout, environment)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _current_report(checkout: Path) -> dict:
    """The report this repository's own auditor source produces, in process."""
    return json.loads(json.dumps(build_api().inspect_build(checkout, checkout / MANIFEST)))


def _bytecode_files(tree: Path) -> dict[str, bytes]:
    return {
        path.relative_to(tree).as_posix(): path.read_bytes()
        for path in sorted(tree.rglob("*.pyc"))
    }


def test_the_poisoned_cache_is_what_an_ordinary_import_executes(poisoned: Trees):
    """The precondition: the cache is usable for the current source, and wrong."""
    header = poisoned.cache.read_bytes()[:16]
    source = poisoned.module.stat()
    assert header[:4] == importlib.util.MAGIC_NUMBER
    assert int.from_bytes(header[4:8], "little") == 0, "timestamp-based"
    assert int.from_bytes(header[8:12], "little") == int(source.st_mtime) & 0xFFFFFFFF
    assert int.from_bytes(header[12:16], "little") == source.st_size & 0xFFFFFFFF
    assert FORGED_CLASSIFIER not in poisoned.module.read_bytes()

    status, recipe_id = _ordinary_audit(poisoned)

    assert status == "PACKAGING_MANUAL_AVAILABLE"
    assert recipe_id is not None


def test_the_governed_audit_ignores_a_poisoned_adjacent_cache(poisoned: Trees):
    before = _bytecode_files(poisoned.auditor)

    completed = _governed_audit(poisoned)

    report = json.loads((poisoned.checkout / REPORT).read_text(encoding="utf-8"))
    assert completed.returncode == 1, completed.stderr
    assert (completed.stdout.strip(), completed.stderr) == ("BUILD_TOOLCHAIN_BLOCKED", "")
    assert report["build_recipe_id"] is None
    assert report == _current_report(poisoned.checkout)
    # Nothing beside the source was purged, rewritten or added to get there,
    # and the poison is still live for anything importing the ordinary way.
    assert _bytecode_files(poisoned.auditor) == before
    assert _ordinary_audit(poisoned)[0] == "PACKAGING_MANUAL_AVAILABLE"


def test_consecutive_audits_compile_into_their_own_directory_outside_every_checkout(
    poisoned: Trees,
):
    probe = poisoned.temp.parent / "probe.txt"
    reports = []
    for _ in range(2):
        completed = _governed_audit(poisoned, **{PROBE: str(probe)})
        assert completed.returncode == 1, completed.stderr
        reports.append((poisoned.checkout / REPORT).read_bytes())

    # Only the current source writes the probe: a run that executed the stale
    # cache would have left no line at all.
    cached = [Path(line) for line in probe.read_text(encoding="utf-8").splitlines()]
    assert len(cached) == 2
    assert all(path.is_relative_to(poisoned.temp) for path in cached)
    directories = [
        poisoned.temp / path.relative_to(poisoned.temp).parts[0] for path in cached
    ]
    assert directories[0] != directories[1]
    for directory in directories:
        assert directory.name.startswith(BYTECODE_DIRECTORY_PREFIX)
        assert not directory.exists(), "removed when its invocation ended"
        for checkout in (poisoned.checkout, poisoned.auditor, REPO_ROOT):
            assert not directory.is_relative_to(checkout.resolve())
    assert list(poisoned.temp.iterdir()) == []
    assert reports[0] == reports[1]


def _preloaded_by_sitecustomize(trees: Trees, site: Path) -> None:
    (site / "sitecustomize.py").write_text(f"import {POISONED_MODULE}\n", encoding="utf-8")


def _left_without_its_source(trees: Trees, site: Path) -> None:
    shutil.copyfile(trees.cache, trees.module.with_suffix(".pyc"))
    trees.module.unlink()


@pytest.mark.parametrize("arrange", [_preloaded_by_sitecustomize, _left_without_its_source])
def test_auditor_code_this_invocation_did_not_compile_is_refused(
    poisoned: Trees, tmp_path: Path, arrange,
):
    """Isolation governs only what an invocation compiles itself.

    A module loaded before it began — here by `sitecustomize`, from the
    poisoned cache — or loaded from bytecode with no source to compile would
    carry the forged classifier straight past it, so the run refuses.
    """
    site = tmp_path / "site"
    site.mkdir()
    arrange(poisoned, site)

    completed = _governed_audit(poisoned, import_path=(site, poisoned.auditor))

    assert completed.returncode == 2
    assert POISONED_MODULE in completed.stderr
    assert not (poisoned.checkout / REPORT).exists()


def test_the_audit_refuses_a_bytecode_directory_inside_the_checkout(tmp_path: Path):
    checkout, _ = make_repo(tmp_path)
    inside = checkout / "scratch"
    inside.mkdir()

    completed = _run([str(CLI), "--check"], checkout, _environment(inside))

    assert completed.returncode == 2
    assert "inside the checkout" in completed.stderr
    assert list(inside.iterdir()) == []
    assert not (checkout / REPORT).exists()


def test_the_entry_point_refuses_to_run_as_an_imported_module(tmp_path: Path):
    """Loaded with `-m`, the entry point's own code may come from a cache."""
    tools = tmp_path / "copy/tools"
    tools.mkdir(parents=True)
    (tools / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(CLI, tools / "build_muejeje_pts.py")
    temp = tmp_path / "temp"
    temp.mkdir()
    arguments = ["-m", "tools.build_muejeje_pts", "--check"]

    completed = _run(arguments, tools.parent, _environment(temp))

    assert completed.returncode == 2
    assert "run this file by path" in completed.stderr
    assert not (tools.parent / REPORT).exists()


def test_isolation_changes_neither_the_report_nor_the_recipe(tmp_path: Path):
    """The directory is how a run compiled the auditor, not what it audited.

    This run imports the auditor the way the governed command does, with no
    import path of its own, so what it compiles is this checkout's source.
    """
    checkout, _ = make_repo(tmp_path)
    temp = tmp_path / "temp"
    temp.mkdir()

    completed = _run([str(CLI), "--check"], checkout, _environment(temp))

    written = (checkout / REPORT).read_text(encoding="utf-8")
    assert completed.returncode == 1, completed.stderr
    assert json.loads(written) == _current_report(checkout)
    assert BYTECODE_DIRECTORY_PREFIX not in written
    assert list(temp.iterdir()) == []
