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
- **PT abbreviates the interface in this table** (`Fa0/1`) while the catalog,
  the fixture and the `interface FastEthernet0/1` used to mutate it all say the
  long form. A textual comparison returns "row absent" — which in this
  calibration means "not delivering" — for a port that is delivering. Lookup
  canonicalizes the alphabetic prefix through a closed alias table and compares
  the numeric remainder verbatim, so `Fa0/1` can never collapse into `Fa0/10`.

`classify_poe_inline_delivery(output, interface, capture_complete)` gates only
the NEGATIVE on completeness. A row that is present and powered is positive
evidence on its own; an absence in an incomplete capture stays `UNOBSERVABLE`.

## Productive API

```text
GovernedPoEInlineObserver.observe_poe_inline_status(
    exact_switch_identity,
    exact_expected_ports,
)
```

The rule alone left the caller to wire freshness, completeness, dispatch
integrity and switch attribution by hand, and every one of those fails in the
dangerous direction: passing `capture_complete=True` over a truncated capture
turns a page break into a negative on a powered port. The observer takes an
identity and ports — never a command; there is no parameter through which IOS or
JavaScript could arrive — refuses malformed input before Packet Tracer is
touched at all, and returns `UNOBSERVABLE` with a reason for every gate it
cannot satisfy rather than reporting an unproven negative.

It was exercised live, not only against replayed bytes, in run `poe1-c5626851`
from frozen source `1e145e8` with Actions green 4/4. The wiring from the
governed executor into the observer — attribution, freshness, privileged-EXEC
entry and restore — cannot be proven with recorded text, which is precisely
where the interface-abbreviation defect above had been hiding.

| state | raw table | productive API | agree |
| --- | --- | --- | --- |
| `auto` | `Fa0/1` row present, `on`, `10.0` | `delivering` | yes |
| `never` | `Fa0/1` row absent | `not_delivering` | yes |
| `auto` | `Fa0/1` row present, `on`, `10.0` | `delivering` | yes |

Four captures, zero refusals, all complete, restoration clean
(`problems: none`). The API's conclusion is stored alongside the raw output and
never in place of it, so any future disagreement stays visible in the evidence
instead of being hidden behind whichever one was written down.

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

End-to-end run of the productive API:

```text
docs/reference/cp-scale/canonical-live-evidence/poe-inline-calibration-poe1-c5626851.json
sha256 f870b200d14e79c6a11bd656664f543fa5b91da9c41ab6310cf1ff3cd4584dd8
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
