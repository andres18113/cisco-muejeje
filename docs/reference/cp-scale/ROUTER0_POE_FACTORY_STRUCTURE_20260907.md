# Factory structure observed, and what it settles — 2026-09-07

Checkout `cplive-ripv2`, branch `feature/runtime-ripv2`, frozen source
`cf89481fa3eaf9efd46c2778cb33b789d2e1197d`, GitHub Actions 4/4 success on that
exact SHA, worktree clean, Packet Tracer `9.0.1.0858`.

This record adds read-only factory evidence and three product fixes. It grants
no LIVE authority, promotes no capability, and does not change `poe_ports`.
Router0 remains not admitted, its single authorization unconsumed, and Router3
not executed.

## 1. Bridge polling: cause found, polling restored

The previous session's read-only preflight was refused because the bridge saw
`connected=false, last_poll_ago=null` for its whole 20 s window, and recorded
that as a channel-availability problem needing the operator.

The cause was local and mundane. Port `54321` is fixed on both sides, and an
unrelated `pytest` process — the PATH interpreter, from concurrent `.pts` work
in the neighbouring checkout — held the `LISTEN` socket on it and did not
answer `/ping` within two seconds. Packet Tracer's webview was polling the
foreign listener, so a bridge started here could never see a poll.

Once that process exited, a fresh `PacketTracerHttpTransport` connected
immediately: `connected=true`, `last_poll_ago=0.1`, `unauth_count=0`,
`Origin: pt-sm:`, `QtWebEngine/6.8.7`. This was not product code, not Script
Module state, not Control Center state, and not an operator UI action.

The practical consequence is a rule, not a fix: a governed runtime boundary
must not overlap a test run in any checkout on this machine, because the
default bridge port is shared process-wide and the poller cannot tell two
listeners apart.

## 2. Three product defects, each measured against 9.0.1.0858

The factory query reached Packet Tracer for the first time and was refused by
our own validation on every model that matters. Each refusal was ours.

| Defect | What Packet Tracer returned | Effect |
| --- | --- | --- |
| Per-node model required non-empty | `AccessPoint-PT` chassis root, and its second slot, report `model: ""` | A complete, correctly attributed answer was discarded as `malformed factory tree metadata` |
| 64-node / depth-8 ceiling | The exact `7960` and `3650-24PS` trees are larger | Both came back as `incomplete or oversized descriptor tree`; their slot inventory was unreadable |
| DeviceType taken only from the catalog category | `getDescriptor(eSwitch, "3560-24PS")` returns nothing | Both PoE switches were unreadable; they are filed under `eMultiLayerSwitch` |

Fixed in `cf89481` with causal RED tests first. Attribution stayed strict: the
top-level identity echo is still exact, `device_type` accepts only values
Packet Tracer documents, and a bounded walk marks every node whose children it
omitted, so a truncated subtree stays visibly absent and can never be read as
an observed absence.

## 3. What was observed

Run `factory-survey-9f967ef6`. Zero mutations, zero qualifications, zero
Router0 attempts consumed. Workspace empty before and after, Realtime
unchanged, canonical `.pts` byte-identical, bridge authenticated with zero
unauthenticated requests.

ModuleType values are read from the installed Cisco reference at
`help/default/IpcAPI/class_module_descriptor.html`, never guessed:
`4 ePtSwitchModule`, `11 eIpPhonePowerAdapter`, `18 eNonRemovableModule`,
`31 eAccessPointPowerAdaptor`.

| Exact model | DeviceType | `11` | `31` | `4` | Root slot types |
| --- | --- | --- | --- | --- | --- |
| `7960` | 12 | **true** | false | — | `[18]` |
| `AccessPoint-PT` | 7 | false | **false** | — | `[6, 18]` |
| `3650-24PS` | **16** | — | — | **true** | `[18, 18, 18]` |
| `3560-24PS` | **16** | — | — | false | `[18]` |
| `2960-24TT` | 1 | — | — | false | `[18]` |

Evidence:

```text
docs/reference/cp-scale/canonical-live-evidence/factory-structure-20260907T003018Z-cf89481fa3ea-observed.json
SHA256 fa5747e56dfa000d6cc3e2c2bdd57ebf33e34b8cfddd109ed34299394220937a
```

## 4. What it settles, and what it does not

**The AccessPoint-PT arms were not unlucky.** Packet Tracer defines
`eAccessPointPowerAdaptor`, and the exact model `AccessPoint-PT` does not
support it — nor any other documented power-adapter type. The exact endpoint
model that already qualified positively, `7960`, does support
`eIpPhonePowerAdapter`. The controls hold in both directions: the phone
refuses the AP's adapter type, and the AP refuses the phone's.

Every governed positive requires a differential against an endpoint whose
external supply can be withheld. That is the measured reason the four
AccessPoint-PT episodes returned UNKNOWN, and it is why repeating them
unchanged cannot produce a positive.

This is structural evidence. It is **not** a behavioural proof that no
`AccessPoint-PT` can ever be powered by PoE, and it must not be recorded as
`supports_poe = UNSUPPORTED` for any switch. It establishes that the
observation the contract demands cannot be constructed for this endpoint model
by creating a fixture and withholding its adapter.

**It is not specific to the bound model either.** A second read-only survey,
`factory-survey-102006c6`, asked the same question of every generic access
point in the catalog:

| Exact model | `isModuleTypeSupported(31)` |
| --- | --- |
| `AccessPoint-PT` | false |
| `AccessPoint-PT-A` | false |
| `AccessPoint-PT-N` | false |
| `AccessPoint-PT-AC` | false |
| `LAP-PT`, `3702i`, `802`, `803` | no descriptor under `eAccessPoint` — unobservable, not a measured absence |

All four generic models expose the same chassis shape: root slots `[6, 18]`
with a repeater NM and one non-removable module. Swapping the design to a
sibling access point would therefore not make the access-point bindings
qualifiable. The four models the factory does not answer for at that
DeviceType are unobservable there, and none of them is bound by the physical
design, so nothing is concluded from them.

```text
docs/reference/cp-scale/canonical-live-evidence/factory-structure-20260907T005226Z-86c75f1c304c-accesspoint-family.json
SHA256 5549a9a30da2eda5aba4c8bae89279b413399073f9dcf396d5639cb41a7463c0
```

**The 3650 supply clue is now named, not resolved.** `3650-24PS` supports
`ePtSwitchModule`, which is the type the productive catalog gives
`AC-POWER-SUPPLY` and `POWER-COVER-PLATE`, and its root exposes three
non-removable slots against one on the `3560-24PS`, which supports no such
module. That is consistent with the two empty supply bays seen in Physical
view and with the `%ILPOWER-5-ILPOWER_POWER_DENY` boot line, and consistent
with the 3560 delivering PoE with no module at all. It does **not** establish
that installing a supply enables inline power. Only a governed observation
could, and none has been made.

The earlier note that the catalog's `module_type=4` meant a power supply in
Cisco's enum was wrong: `4` is `ePtSwitchModule`. The catalog places
`AC-POWER-SUPPLY` in that module class; the two numbering schemes agree here
by class, not by name.

## 5. Exact remaining demand for Router0 admission

Rederived from source at `cf89481`, not from any handoff. `HardwarePlan`
admits a device only when `supports_poe` is SUPPORTED, `poe_ports` covers its
demand, and every exact `(switch port, endpoint model, endpoint port)` triple
is in `poe_authorized_bindings`. The composer requires the whole physical
design, not only Router0's own ports.

| Model | Max simultaneous on one device | Distinct bindings needed | Held today |
| --- | --- | --- | --- |
| `3560-24PS` | 23 (`Switch5`) | 30 — `7960/Switch` on `Fa0/1`–`Fa0/21`, `AccessPoint-PT/Port 0` on `Fa0/{4,5,13,14,15,16,21,22,23}` | 1 binding, capacity 1 |
| `3650-24PS` | 12 (`MLS3`) | 13 — `7960/Switch` on `Gi1/0/{2,3,5..13}`, `AccessPoint-PT/Port 0` on `Gi1/0/3`, `Gi1/0/4` | none; capability UNKNOWN |

Composition is `unresolved`; the canonical pipeline refuses before its first
stage. The ordered stages are `routing-core`, `router4-switch10`, `floor1`,
`floor2`, `floor3`, `router0-branch`, `router3-branch`, `remaining`, and every
one of them projects from a composition that must first be valid. Voice,
routing/control plane, IoT and cleanup are all downstream of that gate.

Of the 43 required bindings, 11 are `AccessPoint-PT`. Under section 4 those 11
cannot be qualified by creating a fixture and withholding an adapter.

## 6. The one thing that needs a person

`GovernedPoEDeliveryObserver` converts exactly one synchronous, identity-bound
visual receipt into evidence, inside `observe(...)`, before its deadline. There
is no product-internal substitute, and that is deliberate: the contract forbids
inferring delivery from catalog metadata, link state, DHCP, forwarding,
`getPower()`, `isPowerOn()` or administrative power state, so the only
admissible observation is somebody looking at the endpoints.

Everything that does not need a person is done: bridge restored, the three read
defects fixed and shipped green, the factory evidence acquired and persisted,
and the demand rederived exactly.

What remains needs the operator in front of Packet Tracer, per episode: a
governed fixture is built, `CAPTURE_PENDING` is printed with the run identity,
fixture fingerprint, deadline and exact bindings, and a `receipt.json`
validating as `PoEVisualCaptureReceipt` must come back inside the window,
recording per binding whether the endpoint is powered, and whether the
observation was simultaneous.

Nothing here weakens the PoE contract, and `poe_ports` stays 1.
