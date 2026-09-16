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

`iot_function` is a separate declaration. This phase does not attempt to
demonstrate smoke detection, motion detection or video, and the function
declaration carries no association field, so no association evidence can be
read as function evidence.

## Packet Tracer capability audit

Audited on Packet Tracer 9.0.1.0858. Every record names the surface it came
from. Graphical proximity on the canvas is not evidence, and an API nobody has
called is UNKNOWN, not UNSUPPORTED.

| Capability | Status | Ground |
| --- | --- | --- |
| Radio enablement (`Laptop-PT`) | SUPPORTED | `Device.addModule(slot, PT-LAPTOP-NM-1W)`, driven by `swapLaptopToWireless` and the production generator |
| Radio enablement (any other model) | UNKNOWN | No module-swap path is registered, and no IoT model has a measured port inventory |
| Service set configuration | UNSUPPORTED | SSID and WPA2 are not exposed through the Script Engine; they are GUI-only |
| Endpoint service set selection | UNKNOWN | Only default-service-set auto-association is described |
| Association state observation | UNKNOWN | The governed policy records wireless association as unqualified: unmeasured, not refuted |
| Associated access point identification | UNOBSERVABLE | A wireless link is enumerated through a single `getPort()`, which names one radio owner and never both ends |
| Wireless port classification | SUPPORTED | `Port.isWirelessPort()`, already read through the port inventory |
| Access point radio port identity | UNKNOWN | `AccessPoint-PT` measures as `Port 0`, `Port 1`; neither was classified |
| Endpoint address observation (`Laptop-PT`) | SUPPORTED | The qualified named-interface getter path, with `Wireless0` as the interface |
| Endpoint address observation (IoT models) | UNKNOWN | The getter resolves a port by name, and no IoT model has a measured interface name |
| DHCP client flag observation | SUPPORTED | `Port.isDhcpClientOn()` — a configuration read-back, not a lease |
| Network attachment observation | UNKNOWN | No registered primitive returns lease state |
| IoT function observation | UNKNOWN | Deliberately not attempted in this phase |

The consequence is exact: on this build the pipeline reaches
`UNOBSERVABLE_BACKEND` for association and attachment, and no run can reach
`ASSOCIATED`. The adapter enforces that rather than working around it — it
issues no association script at all, and it drops an access-point identity that
the audit does not license.

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

- Whether a Packet Tracer association is readable at all on 9.0.1.0858.
- Which `AccessPoint-PT` port is a radio.
- Whether IoT models expose ports, and under which names.
- Whether a DHCP lease is observable for a wireless endpoint.

Each of those is an UNKNOWN with a named surface that would resolve it, which is
what makes a first bounded live probe a small, closed piece of work rather than
an exploration.
