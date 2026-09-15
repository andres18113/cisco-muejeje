# Expansion Modules

The catalog includes expansion modules: WICs, HWICs, NIMs, NMs, SFPs, and
wireless and cellular adapters. Use `pt_list_modules` to discover exact names,
optionally filtered by `router_model` or `category`, then `pt_add_module` for one
module or `pt_install_modules_batch` for several.

## The `slot` argument is a string, not an integer

Packet Tracer compares the slot with `===` against its internal map. Passing `0`
as an integer does not match `"0/0"`, and `addModule()` returns `false` without
reporting an error. Always pass a string literal.

| Slot type | Format | Example |
|-----------|--------|---------|
| HWIC on 1941 / 2901 / 2911 | `"0/0"`, `"0/1"`, `"0/2"`, `"0/3"` | `pt_add_module("R1", "0/0", "HWIC-2T")` |
| NIM on ISR4321 / ISR4331 | `"0/1"`, `"0/2"` (chassis/subslot — not `"0"`/`"1"`) | `pt_add_module("R1", "0/1", "NIM-2T")` |
| NM on 2811 / 2620XM / Router-PT | `"1"` | `pt_add_module("R1", "1", "NM-4A/S")` |
| Cloud / hosts | `"0"`, `"1"`, … `"7"` | `pt_add_module("Cloud", "0", "PT-CLOUD-NM-1S")` |

## Compatibility

- **2911 / 2901 / 1941 (ISR G2)** — HWIC/WIC only, no NM. For four serial ports,
  install two `HWIC-2T` in slots `"0/0"` and `"0/1"`.
- **ISR4321 / ISR4331** — NIM only: `NIM-2T` for serial, `NIM-ES2-4` for GigE.
- **Router-PT** — `PT-ROUTER-NM-*` in slots `"0"` to `"6"`.

## Port naming

Ports are named `<type><chassis>/<subslot>/<port>`:

- `HWIC-2T` in slot `"0/0"` → `Serial0/0/0`, `Serial0/0/1`
- `HWIC-2T` in slot `"0/1"` → `Serial0/1/0`, `Serial0/1/1`

## Installing several at once

Prefer `pt_install_modules_batch`. It powers the device off, adds every module,
and powers it on again in a single `runCode` call. Separate `pt_add_module` calls
power-cycle the device once each, which is slower and can make one call report a
timeout while the reboot is still finishing.

```text
pt_install_modules_batch([
  {"device": "R1", "slot": "0/0", "module": "HWIC-2T"},
  {"device": "R1", "slot": "0/1", "module": "HWIC-2T"}
])
# → Serial0/0/0, 0/0/1, 0/1/0, 0/1/1
```
