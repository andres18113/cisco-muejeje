# MCP Resources

Besides tools, the server exposes read-only MCP resources that a client can fetch
directly for context. All of them return JSON.

| URI | Contents |
|-----|----------|
| `pt://catalog/devices` | Every device model with `display_name`, `category` and exact `ports`. |
| `pt://catalog/cables` | The cable-type catalog (name → Packet Tracer type id). |
| `pt://catalog/aliases` | Friendly aliases → canonical model names (for example `router` → `2911`). |
| `pt://catalog/templates` | Topology templates with descriptions, router ranges and tags. |
| `pt://capabilities` | Server capabilities, version, and the active public surface. |

Resources suit context: the model reads a whole catalog once. For queries against
a running topology, use the tools `pt_query_topology` and `pt_export_topology`
instead.
