"""Reproduce the legacy dual-namespace identity defect in an isolated process."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ENVIRONMENT = REPOSITORY_ROOT / ".venv"

CHILD_SOURCE = r"""
import json
import sys
from pathlib import Path

import packet_tracer_mcp as production_package
import src.packet_tracer_mcp as legacy_package
from packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus as ProductionCapabilityStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus as LegacyCapabilityStatus,
)

root = Path.cwd().resolve()


def relative_origin(module):
    return Path(module.__file__).resolve().relative_to(root).as_posix()


print(
    json.dumps(
        {
            "production_origin": relative_origin(production_package),
            "legacy_origin": relative_origin(legacy_package),
            "physical_origin_same": (
                Path(production_package.__file__).resolve()
                == Path(legacy_package.__file__).resolve()
            ),
            "package_identity_same": production_package is legacy_package,
            "enum_type_identity_same": (
                ProductionCapabilityStatus is LegacyCapabilityStatus
            ),
            "enum_member_identity_same": (
                ProductionCapabilityStatus.SUPPORTED
                is LegacyCapabilityStatus.SUPPORTED
            ),
            "cross_namespace_isinstance": isinstance(
                ProductionCapabilityStatus.SUPPORTED,
                LegacyCapabilityStatus,
            ),
            "loaded_namespaces": sorted(
                name
                for name in ("packet_tracer_mcp", "src.packet_tracer_mcp")
                if name in sys.modules
            ),
        },
        sort_keys=True,
    )
)
"""


def main() -> int:
    """Run the child reproduction and validate the known pre-migration result."""
    executable = Path(sys.executable).resolve()
    if not executable.is_relative_to(EXPECTED_ENVIRONMENT.resolve()):
        print(
            f"Refusing reproduction outside the checkout-local .venv: {executable}",
            file=sys.stderr,
        )
        return 2

    result = subprocess.run(
        [sys.executable, "-c", CHILD_SOURCE],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or "The child process failed.", file=sys.stderr)
        return 2

    observation = json.loads(result.stdout)
    print(json.dumps(observation, indent=2, sort_keys=True))
    expected = {
        "physical_origin_same": True,
        "package_identity_same": False,
        "enum_type_identity_same": False,
        "enum_member_identity_same": False,
        "cross_namespace_isinstance": False,
        "loaded_namespaces": ["packet_tracer_mcp", "src.packet_tracer_mcp"],
    }
    return int(any(observation.get(key) != value for key, value in expected.items()))


if __name__ == "__main__":
    raise SystemExit(main())
