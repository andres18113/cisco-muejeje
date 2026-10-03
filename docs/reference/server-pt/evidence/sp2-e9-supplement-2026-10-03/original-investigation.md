# E9 root-cause investigation

Read-only investigation after the closed E9, while final CI ran. Repository HEAD:
`2d38364dfc5269accc427ae1a99b359b3132d366`. Executed native source:
`ec3b01f84896c9a392f7cc142443460c9d76b8eb`. No new LIVE, replay, source change,
helper modification or episode allocation was performed. This report is a separate
working investigation; it does not alter the sealed E9 archive.

## Finding

The software has a confirmed acquisition-order gap: E5 applies client DHCP mode
before E6 enables the server, and the ordinary mode helper sets
`device.setDhcpFlag(true)` without an explicit post-enable `dhcpRun` acquisition.
This does not by itself prove why native acquisition differed between clients.
The strongest remaining hypothesis is timing/native retry or scheduling asymmetry;
the native mechanism and exact acquisition onset are unobserved.

All eleven mode readbacks and all three pool configurations/direct states verified.
E6 effects were seven applied and three reasserted, accepted/correlated. Pool
dependencies configure serverPool, BR2_DATA and BR1_DATA before native enable,
then reassert the named enable actions. There is no demonstrated pool-after-enable
defect. BR1-PC02 uses the same ordinary batch as its two failed peers, with no
unique explicit-acquisition path. Source: apply_enterprise_services.py:2064;
enterprise_configuration_runtime.py:1997,2085; service_compiler.py:233;
EXTENSION/script-engine/main.js:280.

## Observed difference

BR1-PC02 is APIPA 169.254.6.39/16 with no joined row in BR1 samples 1 and 2.
Sample 3 first observes 10.80.16.2/28, MAC `00E0.8F11.0627` and an exact BR1_DATA
row on FastEthernet0; samples 3 through 13 remain joined. Its two same-segment
peers stay APIPA throughout all 13 snapshots. PC02 alone verifies lease, gateway,
resolver, DNS and both HTTP paths. The other ten lease checks fail; 70 downstream
checks are dependency-blocked. This is genuine partial acquisition, not merely
a missing mode application. See product/2026-10-03T15-26-34Z-cb6c7f70-product.json
under the committed e9 archive, lines4342-4673 and5096-5099, and JSON path
/service_result/verification_results/7/observed.

Group windows were observed sequentially BR2, BR1, HQ, with monotonic starts
56548.937, 56713.375, 56877.765 and about 164 seconds each. The successful BR1
sample starts at +27.468s within its own window. Source/batching reconstruction
associates remote-mode batch seq 275 at 473.328s, server-enable seq 334 at 575.453s,
and successful snapshot seq 367 at 771.515s. Those action-to-sequence assignments
are reconstructed, not recorded payload/action timestamps: the action journal
timestamps are null and purposes are generic. They must not establish onset or
packet causality. Product lines5098,5323,5608; qualification lines3705,4413,4809.

The server static-address check has gateway/DNS getters unobservable, while
IP/mask verify. This does not alone explain the same-segment split or five local
HQ failures, and PC02 completes server-dependent traffic. Later BR2
not_observed=dependent_never_became_admissible is downstream of failed leases;
prelease BR1/BR2 access and routed readiness were admitted. Product:2108,
11089-12531,13888-14172.

E8 and E9 retained plans have identical topology, manifest, E5, normalized-E6 and
service-catalog binding hashes and identical selected clients. In-memory pure
recompilation also matches E9's archived E5/E6 semantic hashes. Source runtime
sequences and simulated hybrid tests cannot establish native retry behavior.

## HTTP Offline indicator

The operator clarified Bridge HTTP / Bridge: offline. The maintained webview
polls authenticated `GET http://127.0.0.1:54321/status` every 2 seconds with a 2-second XHR
timeout;401, other non-200, error, timeout, JSON/handler exception all paint Offline.
interface.js:339-402,591-606. The Python HTTP daemon/token/response must therefore
be checked separately; current post-retirement passive inspection found zero
listeners on 54321. This current observation does not identify the historical
HTTP failure at the operator's report time.

The governed file channel is independent: main.js:91-100,144-194,352-366 starts
its file timer and heartbeat without the UI's S.bridgeUp. File qualification
creates FileBridge; only the HTTP branch starts PacketTracerHttpTransport
(service_qualification.py:1046-1059). The file badge is itself refreshed only
inside successful HTTP status handling (interface.js:372-421), so it may be stale.
The file qualification path neither requires nor starts the HTTP listener.

## Forensic limitation

The 535 ledger operations comprise 532 accepted and 3 acceptance_unknown/
not_observed rows: seq 150, 172, 214 with caps 0.593, 0.532, 0.516 seconds. Their generic
send_and_wait purpose contains no script/action/reader/effect-kind identity.
They cannot conclusively be classified as readers or mutations from the archived
per-operation metadata. None-return and exceptions share this representation
(ledgered_transport.py:88-106), and send_and_wait can carry either effect or getter.
Do not describe the file transport as flawless, or infer replay entitlement.
These rows do not prove an HTTP failure or the DHCP mechanism.

## Minimal next discrimination

Passively capture the HTTP indicator's Terminal message and 54321 listener/owner
while visible: a token rejection separates auth; no listener separates daemon
absence; Bridge unreachable alone cannot distinguish XHR error from timeout.

Offline instrumentation should retain per-dispatch action/reader ID, effect kind,
payload digest and evaluation timestamps. A delayed-one-client simulated case
can guard refusal/no-arm behavior, but cannot select a native retry hypothesis.
A fresh separately authorized exact-scope episode would need all-client state
and native DHCP/event/packet evidence around enable while preserving the approved
three arms and precondition. No restart, pool rewrite,unknown-outcome replay or
new LIVE is performed by this investigation. The exact native cause remains open.

Operator UI actions before the first positive PC02 observation are not bound by
the sealed records. A retrospective operator clarification was requested; any
response is supplemental context, not a rewritten native operation trace.
