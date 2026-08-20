from __future__ import annotations

import os
from collections.abc import Mapping
from enum import Enum


PUBLIC_MCP_SURFACE_ENV_VAR = 'PT_MCP_PUBLIC_SURFACE'


class PublicMcpSurface(str, Enum):
    ENTERPRISE = 'enterprise'
    DEVELOPER_CAPABILITY_INVESTIGATION = 'developer-capability-investigation'


def public_mcp_surface_from_env(
    environ: Mapping[str, str] | None = None,
) -> PublicMcpSurface:
    source = os.environ if environ is None else environ
    value = source.get(PUBLIC_MCP_SURFACE_ENV_VAR)
    if value is None:
        return PublicMcpSurface.ENTERPRISE

    normalized = value.strip()
    try:
        return PublicMcpSurface(normalized)
    except ValueError as exc:
        allowed = ', '.join(surface.value for surface in PublicMcpSurface)
        raise ValueError(
            f'{PUBLIC_MCP_SURFACE_ENV_VAR} must be one of: {allowed}',
        ) from exc
