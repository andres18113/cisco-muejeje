"""Read-only Muejeje build-input check; this does not compile a .pts file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from packet_tracer_mcp.infrastructure.pts import inspect_build
from packet_tracer_mcp.shared.utils import resolve_within


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--builder", type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    manifest = resolve_within(root, "EXTENSION", "manifest", "muejeje-build-manifest.json")
    report = inspect_build(root, manifest, builder_path=args.builder)
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
        report_path = resolve_within(dist, "muejeje.build.json")
    except ValueError:
        return 2
    report_path.write_text(
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(report["status"])
    return 0 if report["build_recipe_id"] is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
