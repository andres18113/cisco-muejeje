# Where the access-point PoE requirement came from — 2026-09-07

An offline provenance audit of `requires_poe` for `DeviceRole.ACCESS_POINT`,
run against source, git history and the admitted references. No Packet Tracer
session was opened and no LIVE was performed.

**Conclusion: it was never a requirement.** It is an implementation assumption
that was later written back into the reference document that appears to justify
it.

## 1. The question

POE-2 measured that a `3560-24PS` delivers nothing to an `AccessPoint-PT` on
`Fa0/13`, and that the PSE table with the AP attached is byte-identical to the
table with nothing attached. That closed the measurement question and opened a
design one: were the access points ever supposed to draw inline power, or did
`required_poe_ports` count them because something assumed they would?

## 2. What the chain actually is

**The admitted reference asks for no power at all.** `topologia_completa_IMP.md`
as admitted in `b4f25bb` — the immutable 279-endpoint reference — contains zero
occurrences of `PoE`, `aliment*`, `power`, `energ*` or any wattage. It pins the
access layer as:

```text
10 Cisco 2960-24TT
```

A build measured to deliver no power on any port. Had access-point PoE been a
requirement, the reference would have been unimplementable on the hardware the
reference itself chose.

**The literal was born unexplained.** `cp_scale.py` was created in `bb383d0`
with:

```python
def _access_points(count: int) -> EndpointRequirement:
    return EndpointRequirement(
        role=DeviceRole.ACCESS_POINT,
        requires_poe=True,          # <- no derivation, no comment, no reference
```

The sibling workload path in the same file derives its value from a functional
property — `requires_poe=role is DeviceRole.IP_PHONE`. The access-point path
asserts a constant.

**The document followed the code, not the other way round.** The `(alimentado)`
annotations beside every access point, and the section *"Por qué los switches de
acceso son PoE — Estos nueve switches alimentan teléfonos IP y access points"*,
were added by `7e5d639` on 2026-08-24, four days after `bb383d0`. That commit
resized the access layer from a powered count of 72 that the literal had already
produced, and swapped nine `2960-24TT` for `3560-24PS` to cover it. The document
restates the assumption; it is not its source.

**The design already flags most of these bindings.** Of the 17 `AccessPoint-PT`
bindings, the `provenance` field marks **10** as `implementation_allocation` and
only 7 as `canonical_reference` — and even those 7 trace to the reference's
*device list*, which says where an access point attaches, never that the switch
powers it.

**Packet Tracer models external AP power directly.** Module type 31,
`ACCESS_POINT_POWER_ADAPTER`, "Power adapter for Access Point".

**And the measurement agrees.** POE-2, bundle `poe2-20260907T173336Z-b4d3459e`:
`auto/off/0.0`, device `n/a`, against `auto/on/10.0` for a `7960` on the same
model and the same port.

Six independent lines, one direction.

## 3. What was corrected

`AccessPoint-PT` is now declared externally powered and consumes no PoE
coverage. `metadata["power_source"] = "external_adapter"` records why.

Per-block `required_poe_ports`, each reduced by exactly its access points:

| Block | Before | After | APs removed |
| --- | --- | --- | --- |
| `zone-a` | 24 | 21 | 3 |
| `zone-b` | 17 | 14 | 3 |
| `zone-c` | 6 | 3 | 3 |
| `zone-d` | 7 | 4 | 3 |
| `mls3` | 12 | 11 | 1 |
| `mls4` | 2 | 1 | 1 |
| `mls5` | 8 | 8 | 0 |
| `mls6` | 1 | **0** | 1 |
| `branch-zone` | 9 | 7 | 2 |
| **total** | **86** | **69** | **17** |

The powered population is now 69 phones and nothing else.

`mls6` is worth naming. Its entire PoE budget was one access point, so the exact
binding POE-2 spent a governed LIVE measuring — `3560-24PS` `Fa0/13` —
existed as a *powered* binding only because of the assumption this audit
retires. Four more switches (`zone-a-01`, `zone-b-01`, `zone-c-01`, `zone-d-01`)
likewise had access-point-only powered demand and now have none.

## 4. What was deliberately not done

**Phones are untouched.** `requires_poe = role is DeviceRole.IP_PHONE` stands. A
`7960` is dark without inline power and draws a measured 10.0W; that is evidence,
not assumption. A regression test guards it against over-correction.

**No endpoint model was substituted.** `AccessPoint-PT` stays, all 17 of them,
on the same switches, the same ports and `Port 0`. `LAP-PT` and `3702i` are not
introduced: no functional requirement asks for them, and retiring a false power
requirement is not permission to redesign.

**No switch model was changed.** Removing demand cannot make a design invalid,
and the hardware plan still validates. Whether the five now-unpowered access
switches should keep `3560-24PS` is a separate question with its own reference
implications; it is not decided here.

**The reference document was not rewritten.** Its access-point `(alimentado)`
annotations are superseded by this audit, but the bytes are left as the
historical record of what `7e5d639` believed. This file is the correction.

**Claim authority is untouched.** `_AUTHORIZED_OBSERVATION_METHODS` remains
`{"manual_visible_power_state"}`. Nothing here promotes, demotes or records any
`supports_poe` value.

## 5. Consequence

`POE_ACCESSPOINT_DIFFERENTIAL_20260907.md` §5 reported eleven `AccessPoint-PT`
bindings blocking `HardwarePlan` admission, and concluded that closing them
needed either a different endpoint model or a second authorized observation
method. There was a third option it did not consider: that the bindings never
needed closing, because they never needed power.

The remaining PoE coverage question is now exactly 69 phone bindings — every one
of them on a device measured to draw 10.0W, and therefore the population a
governed PSE positive could actually serve.

## 6. Verification

```text
tests/test_cp_scale_access_point_power_provenance.py   7 tests, RED before the change
```

RED was confirmed by reverting `requires_poe` to `True`, not assumed. Downstream
expectations updated with their reasons: `86 -> 69` powered endpoints in
`test_cp_scale_canonical_physical.py`, and `29 -> 26` block PoE with
`access_point: 3 -> 0` in `test_cp_scale_poe_authorization.py`.
