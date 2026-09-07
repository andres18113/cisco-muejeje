# POE-1 — `show power inline` calibrated as a PSE delivery observable

Governed run `poe1-c4fae886`, Packet Tracer `9.0.1.0858`, from frozen source
`1d8b568` with GitHub Actions green 4/4.

This record grants no LIVE authority and promotes no capability. It records one
calibrated binding and the typed rule derived from it.

## Why the run existed

The only authorized PoE delivery evidence was `manual_visible_power_state` — a
human looking at a phone. It needs an operator per binding and does not scale to
one more port, and the IPC surface has no inline-power signal
(`inline_power_api_signal = ABSENT_IN_9_0_1_IPCAPI_REFERENCE`). The governed
state named the remaining candidate:

```text
next_observable_candidate =
    SWITCH_SIDE_SHOW_POWER_INLINE_VIA_REGISTERED_IOS_QUERY_NOT_YET_EXAMINED
```

## The binding

```text
3560-24PS  FastEthernet0/1  ->  7960  Switch
no external phone power adapter
```

Disposable fixture, created and deleted by the run. Opening inventory: 0 devices,
0 links, Realtime (`simulation_mode = false`).

## The causal sequence

One sequence on that same exact binding, each state read with a fresh, complete,
single-device-attributed capture, each capture repeated and required to agree
with itself:

| state | `Fa0/1` row | rows | summary `Used` |
| --- | --- | --- | --- |
| `power inline auto` | `Fa0/1 auto on 10.0 IP Phone 7960 3 15.4` | 24 | `10.0(w)` |
| `power inline never` | **absent** | 23 | `10.0(w)` |
| `power inline auto` | `Fa0/1 auto on 10.0 IP Phone 7960 3 15.4` | 24 | `10.0(w)` |

The row appears, disappears and returns identical, in exact response to the
administrative mutation and nothing else. That reversibility is the calibration.

## What the run contradicted

**`never` is an absence, not an `off` row.** The expected signature was
`Oper = off`, `Power = 0`. Packet Tracer does not print the port that way — it
removes the row from the table entirely. So the negative half of the signature
is an absence, which is only assertable from a **complete** capture: in a
truncated one, "absent from the table" and "absent from this page" are the same
bytes. This is why the pager had to be qualified before the rule could exist.

**The summary line does not respond.** `Available:370.0(w) Used:10.0(w)
Remaining:360.0(w)` is byte-identical in all four captures, including `never`
where no port delivers. The summary is recorded and is never authority; only the
row decides.

**`isPortUp()` does not respond either.** Both endpoints read `True` in every
state, so link state is not a PoE proxy and cannot stand in for the row.

## Parser contract

Derived from measured bytes, not from a remembered IOS layout:

- Columns are cut at the widths the rule line declares. The `Device` column
  holds text with spaces (`IP Phone 7960`), so whitespace splitting is wrong.
- The header rule line is the only permission to read rows. Without it there is
  no table — PT answers a command it does not understand with text that would
  otherwise parse.
- The row landing on a pager seam arrives with one leading space (` Fa0/18`).
  Anchoring at line start drops exactly one row per page, and a dropped row is
  indistinguishable from an absent one — it reads as "not powered" on a port
  that is.
- The capture closes with two prompt lines; neither is a row.

`classify_poe_inline_delivery(output, interface, capture_complete)` gates only
the NEGATIVE on completeness. A row that is present and powered is positive
evidence on its own; an absence in an incomplete capture stays `UNOBSERVABLE`.

## Restoration

```text
power inline auto restored and proven by read-back (the auto_2 capture IS it)
endpoint deleted            true
switch deleted              true
session residue retired     Power Distribution Device1
inventory fingerprint       returned to its opening value
Realtime                    restored (simulation_mode = false)
problems                    none
```

The first attempt, `poe1-4d342a1a`, did not restore: deleting both created
devices left a `Power Distribution Device0` that Packet Tracer had placed of its
own accord when the 7960 appeared. That defect was fixed before this run, and
its evidence is retained.

## Claim ceiling

```text
calibrated binding            3560-24PS/FastEthernet0/1 + 7960/Switch
authorized observation methods UNCHANGED (manual_visible_power_state only)
product registry              UNCHANGED (candidate still qualification-only)
poe_ports                     UNCHANGED (1) — no port extrapolation
supports_poe                  UNCHANGED
Router0                       BLOCKED
```

Calibrating an observable is not authorizing a claim with it. Wiring the typed
rule into claim authority is a separate act, on exact governed bindings, with
its own evidence.

## Evidence

```text
docs/reference/cp-scale/canonical-live-evidence/poe-inline-calibration-poe1-c4fae886.json
sha256 b13cad40901a94b957bc6738207e5a8b9505258e96662d3e190b7b3b7e9be104
```

Retained first attempt, restoration incomplete:

```text
docs/reference/cp-scale/canonical-live-evidence/poe-inline-calibration-poe1-4d342a1a.json
```

## Next active step

```text
POE-2 — AccessPoint-PT using the calibrated PSE observable
```

The eleven AccessPoint-PT bindings were unqualifiable because that endpoint has
no removable power adapter, so nothing could be withheld to build a differential.
A switch-side row that responds causally to `power inline` does not need one.
