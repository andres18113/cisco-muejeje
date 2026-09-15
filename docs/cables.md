# Cable Types

Pass a cable type as the last argument of `pt_add_link`, or as a plan link's
`cable`. Omit it to let the server infer the type from the device categories.

| Cable | When to use |
|-------|-------------|
| `straight` | Different device types (router↔switch, switch↔PC). |
| `cross` | Same-type / end-to-end (router↔router, switch↔switch, router↔PC). |
| `serial` | Serial WAN links (needs serial modules — see [Modules](modules.md)). |
| `fiber` | Fiber ports. |
| `console` | Console connections. |
| `roll` | Rollover (console) cable. |
| `phone` | Analog phone lines. |
| `coaxial` | Coax (cable modem / splitter). |
| `auto` | Let Packet Tracer auto-select. |
| `usb` | USB connections. |
| `cable` | Generic copper. |
| `wireless` | Wireless association. |
| `octal` | Octal serial. |
| `cellular` | 3G/4G cellular. |
| `custom_io` | Custom I/O (IoT). |

## Aliases and inference

`pt_add_link` accepts `crossover` (normalised to `cross`) and `rollover`
(normalised to `roll`). When the cable type is omitted, it is inferred from the
device categories.

For a direct `addLink` call in the Script Engine the valid value is `cross`, not
`crossover`. Only `pt_add_link` normalises the alias.
