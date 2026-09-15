# Credits & Attribution

## Upstream project

Cisco-Muejeje started as a fork of
[Mats2208/MCP-Packet-Tracer](https://github.com/Mats2208/MCP-Packet-Tracer)
("Packet Tracer MCP Server"), by Mateo
([@Mats2208](https://github.com/Mats2208)), distributed under the MIT License.
The fork diverged at upstream commit `b075961` (2026-07-31). Several parts come
from that project:

- the MCP server;
- the classic planning, validation and generation pipeline;
- the HTTP bridge and the file bridge;
- the MCP Control Center extension;
- the classic tools.

Work after the divergence point is Cisco-Muejeje's own; see
[NOTICE.md](https://github.com/andres18113/cisco-muejeje/blob/main/NOTICE.md) and
the Git history.

## PTBuilder

[PTBuilder](https://github.com/kimmknight/PTBuilder), by Kim Knight
([@kimmknight](https://github.com/kimmknight)), drives Packet Tracer's Script
Engine from JavaScript. It was the historical starting point and reference for
the Script Engine helper layer, which is the
`addDevice` / `addLink` / `configureIosDevice` style of function that the
extension installs and the script generator emits.

The two projects are separate:

- PTBuilder is its own project by Kim Knight. It is not affiliated with,
  endorsed by, or required by Cisco-Muejeje.
- The PTBuilder repository carries no license, so its files are not
  redistributed here. Building the extension needs local reference copies; see
  `EXTENSION/script-engine/README.md` in the repository.
- To drive Packet Tracer from JavaScript without MCP, use
  [PTBuilder](https://github.com/kimmknight/PTBuilder) directly.

## Built with

- [Model Context Protocol](https://modelcontextprotocol.io): the protocol and
  Python SDK (`mcp[cli]`) that expose the tools to MCP clients.
- [Pydantic](https://docs.pydantic.dev): typed models.
- [Cisco Packet Tracer](https://www.netacad.com/): the network simulator this
  project automates. It is not included, and Cisco-Muejeje is not affiliated with
  Cisco.

## License

The repository is distributed under the MIT License in
[`LICENSE`](https://github.com/andres18113/cisco-muejeje/blob/main/LICENSE). That
file keeps the upstream copyright notice unchanged:
"Copyright (c) 2026 Mateo - Packet Tracer MCP Server".
