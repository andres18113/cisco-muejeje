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

## Deterministic plan delta from `bd097d67b59c491c8aa1a905a10ec48ec079021b`

| Plan | Before | After |
| --- | --- | --- |
| Router0 E4 | `a7ef1872f9ea329a356e89f4546e9edc30130afe8bb1bdadb4bb8bc40030a6f5` | unchanged |
| Router0 E5 | `a39005deea51c03318680de0e4ae4d36b2c7c15a047f536020fc2a454f2347ce` | unchanged |
| Router0 E9 | `b3c9f909ea4812ba35327a26f84ef5f1cd3e2469645f16d284451039b5e93f40` | `ca76501c76b601c2b0463c3bbd2e73479f38c61ec5c9a6ebde04ee977c81227f` |
| Router0 Voice | `e7c9251ef3aa3ebde11e572f83d6f536ddcfb59be6fe1e53f594b857db93694a` | unchanged |
| Full E4 | `599119ec8280e1f7e582a37c540eebcae5dca373b59a77611f60a9340795ef65` | unchanged |
| Full E5 | `b1f351333b205ab8377c01112ce366d690d07e05c0ffeb418dee103257181247` | unchanged |
| Full E9 | `db9a3551276727cfaa9c5cb43535f5f295bdcbc4eb52ee459b3a615937a3a054` | `f94c7552e678b68fbfef9855995f291fc2e1207fb70ec00da2339033dee1c99a` |
| Full Voice | `411478e7435b1e0a288417a5459e004b973f5b21c488c0e7a4f9ac8d2e5f07db` | unchanged |

Observed DHCP addresses belong only to run evidence. They never rewrite these
plans, expectation IDs or hashes. Historical `baseline-v3` is unchanged.
