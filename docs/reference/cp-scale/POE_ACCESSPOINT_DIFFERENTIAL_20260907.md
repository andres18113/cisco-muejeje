# The access-point differential, measured — 2026-09-07

Checkout `cplive-ripv2`, branch `feature/runtime-ripv2`, frozen source
`c4f909ca13e289fd91c6be243de5258c1a2f29d8`, GitHub Actions 4/4 success on that
exact SHA, worktree clean, Packet Tracer `9.0.1.0858`.

Router0 remains not admitted, its single authorization unconsumed, and Router3
not executed. `poe_ports` is unchanged by this record.

## 1. What was asked, and what came back

The previous four access-point episodes returned `unobservable`: nobody was in
front of Packet Tracer inside the five-minute window, so the observer received
no receipt. That is an acquisition failure, not a product fact, and the earlier
note explaining it from factory structure alone said as much — it called itself
structural evidence and refused to promote anything.

Run `r0poe-mls6-a1e7aa15` asked the question again with a person watching. The
fixture is the exact binding the physical design still demands on `MLS6`,
rederived from source at this SHA:

| Arm | Switch | Port | Endpoint | Endpoint port | Observed |
| --- | --- | --- | --- | --- | --- |
| candidate | `3560-24PS` | `FastEthernet0/13` | `AccessPoint-PT` | `Port 0` | **powered** |
| control | `2960-24TT` | `FastEthernet0/1` | `AccessPoint-PT` | `Port 0` | **powered** |

Both arms were read in one simultaneous episode by `andres18113` at
`2026-09-07T02:44:24Z`, method `manual_visible_power_state`, every readiness
prerequisite true, indicator recorded in the observer's own words.

The service classified it `observation_status = observed`,
`verification_status = failed`, `execution_status = verify_failed`, on
`The comparison arm did not provide the required differential power state.`

`supports_poe` stayed **UNKNOWN**. Nothing was promoted, and in particular
nothing was recorded as UNSUPPORTED.

The boundary closed clean: four devices attempted, four deleted endpoint-first,
inventory fingerprint restored, Realtime restored, canonical `.pts` byte
identical before and after, no crash, no unauthenticated bridge request.

```text
docs/reference/cp-scale/canonical-live-evidence/poe-accesspoint-differential-20260907T024424Z-c4f909ca13e2-observed.json
SHA256 7f28f575aee4512bd41dc51b42e00fd09b06dbf6e80d96c1a9022fb40fc2812a
```

## 2. Why this is different from the four UNKNOWN episodes

`unobservable` and `observed but not differential` are not the same claim.
The first says nobody looked. The second says somebody looked and the control
was lit.

That distinction is the whole point of this run. The structural finding —
`AccessPoint-PT` supports no documented power-adapter module type, while the
`7960` supports `eIpPhonePowerAdapter` — predicted this outcome but could not
establish it. It is now established behaviourally.

Note what the fixture does and does not do. It never installs or removes an
adapter. `_create_fixture` creates both endpoints identically and the only
difference between the arms is which switch the link lands on. The `7960`
differential works because a freshly created phone has no supply of its own and
is dark until a PoE port feeds it. `AccessPoint-PT` is lit the moment it exists.

## 3. The endpoint side is out of signals; the switch side is not

The claim contract admits exactly one observation method,
`manual_visible_power_state`, and `_canonical_scope` requires
`comparison_state == "not_powered"` on **every** tested binding in a scope.
Delivery may not be inferred from catalog metadata, link state, DHCP,
forwarding, `getPower()`, `isPowerOn()` or administrative power state.

Every one of those reads the *endpoint*, and that is exactly where this
endpoint has nothing to say. So the first question is whether the IpcAPI offers
any other attributable endpoint signal. It does not. Its complete power surface
is five booleans:

| Class | Methods |
| --- | --- |
| `Device` | `setPower(bool)`, `getPower() -> bool` |
| `Port` | `setPower(bool)`, `getPower() -> bool`, `isPowerOn() -> bool` |
| `ModulePhysicalView` | `setIsPower(bool)`, `isPower() -> bool` |

There is no wattage, consumption, allocation, budget, powered-device class or
`802.3af`/`802.3at` symbol anywhere in the 2205-page reference; the only
`inline` matches are IPS action enums (`eDenyAttackerInline` and siblings).
Every listed method is the administrative/runtime flag the contract already
excludes.

That settles the IpcAPI. It does **not** settle the switch. `show power inline`
asks the delivering end what it is delivering, and the product already has a
governed way to ask: `OperationalQueryId` maps registered query ids to exact
command templates, including per-interface forms such as
`show interfaces {interface}`, read back through the typed IOS channel. A
registered query is not the raw IOS escape the contract forbids; it is the same
mechanism that already carries `show spanning-tree` and `show ip dhcp binding`.

Nothing in this record examined that surface. Whether Packet Tracer's
`3560-24PS` and `3650-24PS` answer `show power inline` at all, and whether what
they answer distinguishes delivery from administrative intent, is unobserved
and is the named next candidate for an E5 observable.

## 4. What this settles, and what it does not

**Settles.** The governed positive the *current* contract requires cannot be
constructed for an `AccessPoint-PT / Port 0` binding on Packet Tracer
`9.0.1.0858`. That contract decides delivery by looking at the endpoint, and
the control state it demands is unattainable for an endpoint that is lit
without inline power. Repeating this episode unchanged cannot produce anything
else.

**Does not settle.** This is not a proof that no access point can receive PoE,
and it is not permission to record `supports_poe = UNSUPPORTED` for any switch.
Whether the candidate arm was lit *by* the 3560 is exactly what the run could
not distinguish, and it stays undistinguished.

Nor does it authorize swapping the design: `AccessPoint-PT-A`, `-N` and `-AC`
expose the same chassis shape and the same refusal of
`eAccessPointPowerAdaptor`, and in any case one endpoint model never authorizes
another.

## 5. Consequence for the canonical composition

Of the 43 exact bindings the design demands, 11 are `AccessPoint-PT` — nine on
`3560-24PS` (`Fa0/{4,5,13,14,15,16,21,22,23}`) and two on `3650-24PS`
(`Gi1/0/{3,4}`). None of them can be covered.

The consequence is sharper than "11 bindings short", because a scope fails as a
whole: a single non-differential binding invalidates the entire episode it sits
in. `Switch5` carries the 23-way maximum demand and two of those 23 are access
points, so its own maximum-capacity episode cannot be run as designed either.
Capacity has to be established from phone-only episodes instead.

Every access switch in the design except `MLS5` carries at least one
access-point binding, and both `3650-24PS` devices do. `MLS5` is therefore the
only one that a complete phone qualification can fully admit.

`HardwarePlan` admission is unreachable while those 11 bindings stand. Closing
them needs either a different endpoint model in the physical design, or a second
authorized observation method in the claim contract. Both are changes to
authority this record does not hold, and neither is invented here.

The second of those is the direction now chosen. An observable read at the
delivering end does not care whether the powered device has its own supply, so
it is the one candidate that could close the access-point bindings rather than
route around them. It has to earn admission the same way this method did:
characterized control, exact identity, fail-closed, bounded observation,
preserved provenance and cleanup, and causal RED tests before implementation.
Until then the 11 bindings stay UNKNOWN.
