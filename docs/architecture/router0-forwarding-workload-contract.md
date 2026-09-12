# Router0 forwarding workload contract

This change replaces the CP-SCALE-only "first static endpoint" forwarding
witness with policy `cp-scale-wired-data-workload@1`. Generic E9 callers do not
inherit this policy: without the explicit argument, historical expectations and
their serialized identity remain unchanged.

The selector runs before any ping and accepts only a projected `user_pc` whose
source requirement marks it as a workload, whose site and DATA segment match
the policy, whose single E5 endpoint action is unambiguous, and whose exact E4
link uses the same endpoint interface. A phone pass-through is a valid cable;
the selector does not require a direct switch attachment. Valid candidates are
ordered by semantic device ID, E5 action ID and link ID. There is no AP or
router fallback.

For the Router0 projection the plan selects, without assigning a LIVE address:

| Site | Endpoint | E5 action | Interface/link | Mode/segment |
| --- | --- | --- | --- | --- |
| Large | `endpoint/large-branch/campus/floor-1/zone-a/user_pc/001` | `cfg/endpoint-dhcp/bb26ab0512f89bb0` | `FastEthernet0` / `link/endpoint_access/5cbe2462c493` | DHCP / `large-branch-data` |
| Multilayer | `endpoint/multilayer-branch/multilayer-campus/access/mls3/user_pc/001` | `cfg/endpoint-dhcp/7aa53dd36126b328` | `FastEthernet0` / `link/phone_passthrough/cdee58ed177a` | DHCP / `multilayer-branch-data` |

At execution, the deployment manifest binds semantic device and link identity
to one runtime target. The one shared getter reads only IPv4 and mask on the
exact interface. DHCP must yield a usable host address inside the E5 network
with the E5 mask; static mode must equal the planned address and mask. Gateway
and DNS remain unclaimed because Packet Tracer exposes no qualified getter for
them. Detectable conflicts cover fixed IPv4 identities in the selected E5 plan
and the co-observed representative bindings; this is not a universal duplicate
address scan.

Each forwarding attempt reads its required endpoint bindings before the typed
ping and again afterward. Identity, address or mask drift invalidates that
attempt, and no other endpoint is selected. A fresh, uniquely attributed ping
with zero replies is a communication failure. A missing/stale channel remains
UNOBSERVABLE and is not a pass.

Router0 retains the router-origin E9/CP-LIVE checks and adds two separately
identified user checks: Large PC to Multilayer PC and the reverse. The latter
execute from the PC runtime terminals; they neither query IOS routes on a PC nor
borrow a router identity. Their scope is exactly one representative pair, not
all hosts, VLANs or throughput.

## Productive plan delta from `bd097d67b59c491c8aa1a905a10ec48ec079021b`

Both sides below use the same persisted real A+B capability store. This keeps
capability provenance fixed while comparing only the base and candidate code.

| Plan | Before | After |
| --- | --- | --- |
| Router0 E4 | `9ea98a4d81bc7e1f19cbb538707569fadbfcb80c4c30bde796b9c3da53f22e67` | unchanged |
| Router0 E5 | `f1edc433281325320d1501b01112aa4b11c9605c70d6ba099bc1200b12bd71a0` | unchanged |
| Router0 E9 | `32a88649cfcb9ab13f1e2766c0c073cabd4ee238bbca141ec6b9d22ee235ff91` | `90eba13a9e288dc803dafb81e639295d0bc0e7de086cb0677fc642fff6f5f5a9` |
| Router0 Voice | `11b24dd089457b0768b21262bb4c769659bc12919e42621b3c8b49ebcc17d4ce` | unchanged |
| Full E4 | `065d06cfe9374c2be9ec80e711913be7339333ed42854359ca640bb8e303c150` | unchanged |
| Full E5 | `9917322f7fcdc9cb6013ef046e7546803fe4ebc4ddd6c6ac63fff005600c1473` | unchanged |
| Full E9 | `b5464bf601de18daa1c85ff1ca224bfbcd97360f596823d0b825572b35769e76` | `15f4347ad11a38864257f42d5dbaab4798add281a11b4602d660703e4954946e` |
| Full Voice | `de3bbb6b350bc27cdfec309e0e9da3ca9583d69704ecda2e8cf23e8447ab1c44` | unchanged |

Observed DHCP addresses belong only to run evidence. They never rewrite these
plans, expectation IDs or hashes. Historical `baseline-v3` is unchanged.
