"""Read-only Muejeje build-input check; this does not compile a .pts file.

This is the command that issues ``PACKAGING_MANUAL_AVAILABLE`` and a
``build_recipe_id``, so the auditor it runs has to be the auditor in the
checkout. Ordinary imports do not guarantee that. Python executes a
timestamp-based ``.pyc`` whenever it records the source's mtime and size, and a
moved or restored tree can keep bytecode compiled from other contents that
still records both — a stale auditor would then issue a verdict the current one
refuses.

So no project module is imported until bytecode is isolated, and until then
only the standard library runs. ``sys.pycache_prefix`` is then pointed at a
directory created for this invocation alone, outside every checkout involved,
and removed when the invocation ends. Every later import reads and writes its
bytecode there, so each auditor module is compiled from its source and no
``__pycache__`` in any tree is read or written. ``-B`` would not do it: it stops
writes, and still reads whatever is there.

The run refuses, before it writes a report, when that is not what happened:
when this file was imported as a module instead of run by path, when the
directory would sit inside a checkout, when an auditor module was loaded before
isolation began, or when one was not compiled from its source into this
invocation's directory. The directory is machine-local, never reported, and no
part of recipe identity.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

PACKAGE = "packet_tracer_mcp"
BYTECODE_DIRECTORY_PREFIX = "muejeje-audit-pycache-"
REFUSED = 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--builder", type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    inherited = sys.pycache_prefix
    prefix = _isolate_bytecode(root)
    if prefix is None:
        return REFUSED
    try:
        return _audit(root, args.builder, prefix)
    finally:
        # The auditor is loaded by now. Whatever is imported while the
        # interpreter exits must not recreate the directory removed here.
        sys.pycache_prefix = inherited
        shutil.rmtree(prefix, ignore_errors=True)


def _isolate_bytecode(root: Path) -> Path | None:
    """Send the bytecode of every later import to a new directory, or refuse."""
    if __spec__ is not None:
        return _refuse(
            "run this file by path; imported as a module, its own code may "
            "have come from a bytecode cache"
        )
    loaded = _project_modules()
    if loaded:
        return _refuse("imported before bytecode isolation: " + ", ".join(loaded))
    base = Path(tempfile.gettempdir()).resolve()
    for checkout in (root, Path(__file__).resolve().parents[1]):
        if base.is_relative_to(checkout):
            return _refuse(
                f"bytecode directory {base} is inside the checkout {checkout}"
            )
    prefix = Path(tempfile.mkdtemp(prefix=BYTECODE_DIRECTORY_PREFIX)).resolve()
    sys.pycache_prefix = str(prefix)
    return prefix


def _audit(root: Path, builder: Path | None, prefix: Path) -> int:
    """Import the auditor, confirm this invocation compiled it, and inspect."""
    from packet_tracer_mcp.infrastructure.pts import inspect_build
    from packet_tracer_mcp.shared.utils import resolve_within

    uncompiled = [
        name for name in _project_modules() if not _compiled_into(name, prefix)
    ]
    if uncompiled:
        _refuse(
            "not compiled from source for this invocation: " + ", ".join(uncompiled)
        )
        return REFUSED
    manifest = resolve_within(root, "muejeje_pts", "manifest", "muejeje-build-manifest.json")
    report = inspect_build(root, manifest, builder_path=builder)
    report_path = _report_path(root)
    if report_path is None:
        return REFUSED
    report_path.write_text(
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(report["status"])
    return 0 if report["build_recipe_id"] is not None else 1


def _report_path(root: Path) -> Path | None:
    """The one report destination, or `None` when writing there is unsafe."""
    from packet_tracer_mcp.shared.utils import resolve_within

    try:
        dist_leaf = root / "dist"
        if dist_leaf.is_symlink():
            raise ValueError("dist destination cannot be a symlink")
        dist = resolve_within(root, "dist")
        dist.mkdir(exist_ok=True)
        report_leaf = dist / "muejeje.build.json"
        if report_leaf.is_symlink():
            raise ValueError("report destination cannot be a symlink")
        if report_leaf.exists() and report_leaf.stat().st_nlink != 1:
            raise ValueError("report destination has multiple hard links")
        return resolve_within(dist, "muejeje.build.json")
    except ValueError:
        return None


def _project_modules() -> list[str]:
    return sorted(
        name for name in list(sys.modules)
        if name == PACKAGE or name.startswith(PACKAGE + ".")
    )


def _compiled_into(name: str, prefix: Path) -> bool:
    """Whether module `name` was compiled from its source file into `prefix`.

    A module loaded any other way — from bytecode with no source beside it, or
    with its cache path fixed before isolation began — ran code this invocation
    did not compile, whatever that code says.
    """
    spec = getattr(sys.modules.get(name), "__spec__", None)
    cached = getattr(spec, "cached", None)
    return (
        isinstance(getattr(spec, "loader", None), SourceFileLoader)
        and cached is not None
        and Path(cached).is_relative_to(prefix)
    )


def _refuse(reason: str) -> None:
    print(f"refusing: {reason}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
