"""
Servidor MCP para Packet Tracer.

Punto de entrada: crea el servidor, registra tools/resources, y arranca
en streamable-http (:39000) o stdio según el flag --stdio.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from mcp.server.fastmcp import FastMCP

from .adapters.mcp.resource_registry import register_resources
from .adapters.mcp.tool_registry import register_tools
from .settings import SERVER_NAME, SERVER_INSTRUCTIONS

TRANSPORT_PORT = 39000

mcp = FastMCP(
    SERVER_NAME,
    instructions=SERVER_INSTRUCTIONS,
    host="127.0.0.1",
    port=TRANSPORT_PORT,
    stateless_http=True,
)

register_tools(mcp)
register_resources(mcp)


def main(argv: Sequence[str] | None = None) -> int:
    """Arranca el servidor MCP.

    Por defecto usa streamable-http en :39000.
    Con --stdio usa transporte stdio (para debug o clientes legacy).
    """
    parser = argparse.ArgumentParser(
        prog="pt-mcp",
        description="Servidor MCP local para Cisco Packet Tracer.",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="usar transporte stdio en lugar de Streamable HTTP (puerto 39000)",
    )
    args = parser.parse_args(argv)

    try:
        mcp.run(transport="stdio" if args.stdio else "streamable-http")
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
