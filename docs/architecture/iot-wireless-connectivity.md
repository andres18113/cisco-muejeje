# IoT Wireless Connectivity

First architectural base for wireless IoT connectivity. It models how an IoT
endpoint reaches a network segment over the air, and it keeps every claim at the
level the evidence actually supports.

Smoke detectors, motion detectors and webcams are the first consumers of this
contract. They are not special cases in it: membership is decided by the
endpoint's own wireless intent, so humiture and temperature monitors — and a
wireless laptop — enter through the same types with no new code.

## The chain

```text
IoT endpoint
  -> wireless cluster            (a service area, one segment, one service set)
     -> candidate access points  (one or more; the backend may still choose)
        -> intended segment      (role, and VLAN/subnet once IPAM has run)
           -> addressing intent  (DHCP, static, unspecified)
              -> association observation
              -> network attachment observation
```

An endpoint is never bound to one specific access point when the backend can
decide the association itself. The plan carries the full candidate set and says
who chooses; pinning is opt-in and has to name a candidate of the cluster.

## Layers

| Layer | Module | Responsibility |
| --- | --- | --- |
| Domain | `domain/enterprise/models/wireless_connectivity.py` | Contracts, state vocabularies, and the two classification functions |
| Domain | `domain/enterprise/rules/wireless_connectivity.py` | Fail-closed validation of plans and of claimed states |
| Domain | `domain/enterprise/services/wireless_cluster_planner.py` | Deterministic derivation of clusters from expanded endpoints |
| Application | `application/ports/wireless_connectivity.py` | The typed boundary a backend implements |
| Application | `application/use_cases/plan_iot_connectivity.py` | Orchestration, acceptance policy, closure |
| Infrastructure | `infrastructure/catalog/wireless_capabilities.py` | The Packet Tracer capability audit, pinned to one build |
| Infrastructure | `infrastructure/execution/packet_tracer_wireless_connectivity.py` | The Packet Tracer adapter |

The domain names no backend. `tests/test_iot_connectivity_architecture.py`
enforces that, along with the application layer depending on the port rather
than on any adapter.

The planner reuses what already exists instead of restating it: `DeviceRole`,
the site/building/floor/zone hierarchy, `NetworkSegment`, `ExpandedEndpoint`
with its source groups and requirement metadata, and the single role-to-segment
policy in `SegmentAssignmentPolicy`. That policy gained one method so an
expanded endpoint can ask the same question an aggregated requirement asks;
nothing else was duplicated.

## States

Association and network attachment are separate axes with the same lifecycle
shape:

| State | Association | Attachment |
| --- | --- | --- |
| PLANNED | the plan exists | the plan exists |
| CONFIGURED | a backend accepted configuration | a backend accepted configuration |
| ASSOCIATED / ATTACHED | a fresh direct reading said so | an address inside the intended segment |
| UNOBSERVABLE | the reading does not exist on this backend | the reading does not exist on this backend |
| FAILED | a fresh reading said not associated | no address, or one outside the segment |
| UNKNOWN | never read, or the reading was stale | never read, or no subnet to compare against |

Configuration never becomes verification. `CONFIGURED` is the ceiling for
anything a backend merely accepted, and the promotion to `ASSOCIATED` requires
a reading that is fresh, observed and carries a named verification method.

Every observation keeps the evidence that produced it: the method, the
observation status, the freshness, the exact backend build, and — when the read
stopped — the interface member it stopped at. A reading names where it ended,
never why.

Three things are kept strictly apart, because rounding any of them together
would let a state claim more than it has:

- **A contradiction is FAILED.** A reading whose endpoint, backend or build
  does not match the subject it is about to be credited to is discarded and the
  state fails. Re-attributing it to the expected subject is the one error
  nothing downstream could detect.
- **A probe failure is UNKNOWN.** A transport exception, a timeout, a
  script-engine error and a malformed payload are four named kinds, each kept
  with the stage it happened at. The property was never asked, so nothing is
  said about it.
- **UNOBSERVABLE is only an absent member.** It means the backend was asked and
  the reading does not exist. An unmeasured capability is not unobservable, and
  a swallowed exception must never appear as one.

## Backend authority

A run states one backend, one exact build and one capability audit, and they
have to agree. When a port is present its own audit is the authority: a
supplied audit that differs in identity or in any single record is refused, as
is an audit holding a record stamped with another build, or a port whose
reported build does not match its own audit.

The refusal happens before the first `configure_association`,
`observe_association` or `observe_attachment`, together with plan validation,
so a rejected run is provably free of side effects rather than merely annotated
after the fact.

## Closure

The closure answers for both axes and the admission together:

| Closure | When |
| --- | --- |
| PLAN_ONLY | no backend was injected |
| INADMISSIBLE | refused before any call, or rejected with nothing left to say |
| CONFIGURED_NOT_OBSERVED | nothing was observed on either axis |
| UNOBSERVABLE_BACKEND | every axis came back as an absent member |
| PARTIALLY_OBSERVED | some members observed, none contradicted |
| FAILED | a fresh contradiction on either axis |
| OBSERVED | every member associated and attached, on an accepted run |

A real failure never degrades into `PARTIALLY_OBSERVED`, and a rejected
admission can never reach `OBSERVED`.

`iot_function` is a separate declaration. This phase does not attempt to
demonstrate smoke detection, motion detection or video, and the function
declaration carries no association field, so no association evidence can be
read as function evidence.

## Packet Tracer capability audit

Audited on Packet Tracer 9.0.1.0858. Three sources feed it and they are not
interchangeable:

- a **measurement** on this exact build is the only thing that makes a
  capability SUPPORTED;
- the **vendor reference** bundled with the product makes it DOCUMENTED;
- everything else is UNKNOWN.

The reference is the Extensions API help shipped inside the 9.0.1.0858
installation, under `help/default/IpcAPI`. Its own title page reads "Cisco
Packet Tracer Extensions API 8.1.0", so the documentation ships one version
behind the binary, and its `Device::getProcess` entry states plainly that "not
all names have an interface to interact with". That is why DOCUMENTED is a
separate class and not a soft SUPPORTED: it gates exactly like UNKNOWN wherever
a promotion is decided.

Graphical proximity is never evidence, and an API nobody has called is UNKNOWN
or DOCUMENTED, never UNSUPPORTED.

| Capability | Status | Ground |
| --- | --- | --- |
| Radio enablement (`Laptop-PT`) | SUPPORTED | `Device.addModule(slot, PT-LAPTOP-NM-1W)`, driven by `swapLaptopToWireless` and the production generator |
| Radio enablement (any other model) | UNKNOWN | No module-swap path is registered, and no IoT model has a measured port inventory |
| Wireless port classification | SUPPORTED | `Port.isWirelessPort()`, already read through the port inventory |
| DHCP client flag observation | SUPPORTED | `Port.isDhcpClientOn()` — a configuration read-back, not a lease, and a disabled flag is not a static assignment |
| Endpoint address observation (`Laptop-PT`) | SUPPORTED | The qualified named-interface getter path, with `Wireless0` as the interface |
| Endpoint address observation (IoT models) | UNKNOWN | The getter resolves a port by name, and no IoT model has a measured interface name |
| Service set configuration | DOCUMENTED | `WirelessCommon.setSsid/getSsid`; `WirelessServerProcess.setAuthenType/setEncryptType/setSsidBrdCastEnabled` via `Device.getProcess("WirelessServer")` |
| Endpoint service set selection | DOCUMENTED | `WirelessClientProcess.setCurrentProfile/addProfile/getCurrentProfile` via `Device.getProcess("WirelessClient")` |
| Association state observation | DOCUMENTED | `WirelessClientProcess.getCurrentApMac/getSsid/getCurrentProfile`; `WirelessCommon.getPort` |
| Associated access point identification | DOCUMENTED | `getCurrentApMac()`; `Antenna.getReceiverCount()/getReceiverAt(int)` with `getPort()` and `Port.getOwnerDevice()` |
| Network attachment observation | DOCUMENTED | `WirelessProfile.isDhcpEnabled/.ipAddress/.subnetMask/.defaultGateway` |
| Access point radio port identity | UNKNOWN | `AccessPoint-PT` measures as `Port 0`, `Port 1`; neither was classified |
| IoT function observation | UNKNOWN | Deliberately not attempted in this phase |

Nothing on this build is recorded UNSUPPORTED: nothing has been measured to be
impossible. The consequence is exact — the adapter drives no documented surface,
so a run on this build reaches `CONFIGURED_NOT_OBSERVED` and never `ASSOCIATED`.

An earlier revision of this table recorded service set configuration as
UNSUPPORTED and access point identification as UNOBSERVABLE. Both were wrong:
they described what this repository drives, not what the backend offers, and
the bundled reference documents `setSsid`, `getCurrentApMac` and the antenna
receiver walk.

## IoT-0: the prepared read-only probe

`infrastructure/execution/iot0_wireless_probe.py` builds the contract for the
first bounded live probe. It is prepared, not run: building a contract is not
executing it, and the module is wired to no transport.

Per endpoint, most authoritative surface first:

1. `Device.getProcess("WirelessClient")` — does the process exist at all;
2. `getCurrentProfile()` → SSID, AP MAC, DHCP flag, IPv4, mask, gateway, VLAN,
   band, strength;
3. `getSsid()`;
4. `getCurrentApMac()`;
5. `WirelessCommon.getPort()` → port name, MAC, `isWirelessPort()`;
6. the full port inventory with name, MAC, radio flag, DHCP flag, IPv4, mask.

Per access point: `Device.getProcess("WirelessServer")`, then SSID,
authentication and encryption type and SSID broadcast, then the radio port
identity and MAC, then the port inventory.

Secondary evidence: the `Antenna` links whose transmitter belongs to the target,
then `getReceiverCount()` and a capped `getReceiverAt(i)` walk, resolving each
end through `Port.getOwnerDevice()`.

Guarantees, each pinned by a test:

- **read-only** — no `set*`, `add*`, `remove*`, `reset*`, `create*` or `apply*`
  call appears in any generated script;
- **no credentials** — `WirelessProfile.key`, `.password` and `.userID` are
  excluded from the projection and absent from every script;
- **bounded** — a fixed step list, one script per block per device, a capped
  receiver walk, and no workspace enumeration;
- **exact-build scoped** — the builder refuses any build but 9.0.1.0858;
- **identity, never position** — pairing comes from MACs and port owners; no
  coordinate is read;
- **every step says where it stopped** — each script reports `stopped_at` with
  the exact member it could not reach.

## Scenarios

`tests/support/iot_connectivity_scenarios.py` holds three shapes:

- simple: one access point and one sensor in one zone;
- medium: several IoT roles and several access points inside one zone;
- advanced: two sites, several zones, and a zone whose wireless laptop forms a
  second cluster because it belongs to a different segment role.

The governed reference design is exercised as a fourth, read-only fixture in
`tests/test_iot_connectivity_reference_topology.py`. It shows a large existing
enterprise plan flowing through the same contract. Its closure is not read,
written or reopened by any of this.

## What is still open

Everything below needs the live probe; none of it can be settled offline.

- Whether `Device.getProcess("WirelessClient")` returns a usable object on
  `Smoke Detector`, `Motion Detector` and `Webcam`, or on any IoT model.
- Whether `getCurrentApMac()` and `getCurrentProfile()` are populated on this
  build.
- Whether `Device.getProcess("WirelessServer")` is reachable on
  `AccessPoint-PT`, and whether SSID and security read back.
- Whether an `Antenna` reports receivers, and whether the walk resolves to the
  devices on both ends.
- Whether IoT models expose ports at all, and under which names.
- Which `AccessPoint-PT` port is a radio.
- Whether addressing observed through a client profile reflects a granted lease
  or only a requested one.

Each is an UNKNOWN or DOCUMENTED entry with a named surface that would resolve
it, which is what makes IoT-0 a small closed piece of work rather than an
exploration.
